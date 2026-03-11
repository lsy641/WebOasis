"""
ActBook Controller - High-level interface for managing operations and execution
"""
import logging
from typing import List, Dict, Any, Optional, Type, Union
from importlib import import_module
from .core.registry import OperationRegistry
from .core.base import Operation, OperationResult
from .core.automator_interface import BrowserAutomator

logger = logging.getLogger(__name__)


class ActBookController:
    """
    High-level controller for managing the act_book system.
    
    This class provides a unified interface for:
    - Listing available operations
    - Executing operations
    - Getting action space descriptions
    - Flexible operation registration (operation-level, category-level, or all)
    """
    
    def __init__(self, auto_register: bool = True, log_level: str = "INFO"):
        """
        Initialize the ActBook controller.
        
        Args:
            auto_register: If True, automatically import and register all operations
            log_level: Logging level for the controller
        """
        self._registry = OperationRegistry
        self._auto_registered = False
        
        # Set up logging
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
        if auto_register:
            self.auto_register_operations()
    
    def auto_register_operations(self) -> None:
        """Automatically import and register all operations from act_book modules."""
        if self._auto_registered:
            self.logger.info("Operations already auto-registered, skipping...")
            return
            
        try:
            self.logger.info("Auto-registering operations from act_book modules...")
            
            # Simple import from operations.py - all operations are automatically registered via decorators
            from . import operations
            
            self._auto_registered = True
            operation_count = len(self.list_operations())
            self.logger.info(f"Successfully registered {operation_count} operations")
            
        except Exception as e:
            self.logger.error(f"Error during auto-registration: {e}")
    
    def register(self, target: Union[str, Type[Operation], List[Union[str, Type[Operation]]]] = None) -> bool:
        """
        Flexible registration function that supports:
        - Operation-level: register(CustomOperation) or register([CustomOperation, AnotherOperation])
        - Category-level: register('browser') or register(['browser', 'dom'])
        - Sub-category-level: register('browser/interaction') or register(['browser/interaction', 'dom/selector'])
        - All operations: register() or register('all')
        
        Args:
            target: Can be:
                - None or 'all': Register all operations in act_book/book
                - Operation class: Register a single operation
                - List of operation classes: Register multiple operations
                - String: Register operations from a category ('browser', 'dom', 'composite') or sub-category ('browser/interaction')
                - List of strings: Register operations from multiple categories/sub-categories
                
        Returns:
            True if successful, False otherwise
        """
        try:
            if target is None or target == 'all':
                # Register all operations (default behavior)
                self.logger.info("Registering all operations from act_book/book")
                return self.auto_register_operations()
            
            elif isinstance(target, type) and issubclass(target, Operation):
                # Single operation class
                self.logger.info(f"Registering operation: {target.__name__}")
                self._registry.register(target)
                return True
            
            elif isinstance(target, list):
                # List of operations or categories
                success_count = 0
                for item in target:
                    if self.register(item):
                        success_count += 1
                
                self.logger.info(f"Registered {success_count}/{len(target)} items successfully")
                return success_count > 0
            
            elif isinstance(target, str):
                # Category or sub-category name
                return self._register_category_or_subcategory(target)
            
            else:
                self.logger.error(f"Invalid target type: {type(target)}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error during registration: {e}")
            return False
    
    def _register_category_or_subcategory(self, path: str) -> bool:
        """Helper method to register operations from a category or sub-category."""
        try:
            self.logger.info(f"Registering operations from: {path}")
            
            # Check if it's a sub-category (contains '/')
            if '/' in path:
                # Sub-category: e.g., 'browser/interaction'
                category, subcategory = path.split('/', 1)
                # Build import path relative to this package (e.g., 'weboasis.act_book.book.browser.interaction')
                module_path = f'{__package__}.book.{category}.{subcategory}'
            else:
                # Category: e.g., 'browser'
                category = path
                subcategory = None
                # Build import path relative to this package (e.g., 'weboasis.act_book.book.browser')
                module_path = f'{__package__}.book.{category}'
            
            # Import the module
            target_module = import_module(module_path)
            
            # Force import to trigger decorators
            _ = target_module
            
            # Count operations in this category/subcategory
            if subcategory:
                # For sub-categories, we need to check if operations were registered
                # by looking at the registry for operations in this category
                category_ops = self.get_operations_by_category(category)
                self.logger.info(f"Sub-category '{path}' registered, found {len(category_ops)} operations in category '{category}'")
            else:
                category_ops = self.get_operations_by_category(category)
                self.logger.info(f"Category '{path}' registered with {len(category_ops)} operations")
            
            return True
            
        except ImportError as e:
            self.logger.error(f"Path '{path}' not found: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error registering '{path}': {e}")
            return False
    
    def list_operations(self) -> List[str]:
        """List all registered operation names."""
        return self._registry.list_operations()
    
    def get_operations_by_category(self, category: str) -> List[str]:
        """Get operations by category."""
        return self._registry.get_operations_by_category(category)
    
    def get_operation_info(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed information about all operations."""
        return self._registry.get_operation_info()
    
    def get_operation(self, name: str) -> Optional[Type[Operation]]:
        """Get an operation class by name. Only auto-registers if the operation is not found and not already registered."""
        # First, try to get the operation from the registry
        operation = self._registry.get_operation(name)
        if operation:
            return operation
        
        # Operation not found - check if we should auto-register
        # Only auto-register if there are no operations registered at all
        # This prevents repeated auto-registration when operations are already registered
        if len(self._registry.list_operations()) == 0 and not self._auto_registered:
            # Temporarily auto-register to find the operation
            self.auto_register_operations()
            operation = self._registry.get_operation(name)
            # Clear after getting the operation since we only needed it temporarily
            self._registry.clear()
            self._auto_registered = False
        
        return operation
    
    def get_operations(self, names: List[str]) -> Dict[str, Type[Operation]]:
        """Get operation classes by names from the registry."""
        return self._registry.get_operations(names)
    
    def get_operation_classes_by_names(self, names: List[str]) -> Dict[str, Type[Operation]]:
        """
        Get operation classes by names without requiring them to be registered.
        Uses auto-register to temporarily make all operations available.
        
        Args:
            names: List of operation names (e.g., ['click', 'navigate', 'type'])
            
        Returns:
            Dictionary mapping operation names (lowercase) to operation classes
        """
        # Check if operations are already registered
        had_existing_operations = len(self._registry.list_operations()) > 0
        was_auto_registered = self._auto_registered
        
        # Temporarily auto-register all operations to make them accessible
        if not self._auto_registered:
            self.auto_register_operations()
        
        # Get the requested operations from the registry
        operations = self._registry.get_operations(names)
        
        # Clear registry if we just auto-registered and there were no existing operations
        # This prevents clearing operations that were manually registered
        if not was_auto_registered and not had_existing_operations:
            self._registry.clear()
            self._auto_registered = False
        
        return operations
    
    def execute_operation(self, operation_name: str, automator: BrowserAutomator, **kwargs) -> OperationResult:
        """
        Execute an operation by name.
        
        Args:
            operation_name: Name of the operation to execute
            automator: Browser automator instance
            **kwargs: Parameters for the operation
            
        Returns:
            OperationResult with success status and data
        """
        try:
            operation_class = self.get_operation(operation_name)
            if not operation_class:
                return OperationResult(
                    success=False, 
                    error=f"Operation '{operation_name}' not found"
                )
            
            # Create operation instance and execute
            operation = operation_class()
            if not operation.validate_params(**kwargs):
                return OperationResult(
                    success=False, 
                    error=f"Invalid parameters for operation '{operation_name}'"
                )
            
            result = operation.execute(automator, **kwargs)
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing operation '{operation_name}': {e}")
            return OperationResult(
                success=False, 
                error=f"Execution error: {str(e)}"
            )
    
    def get_action_space_description(self, preferred_method: str = None) -> str:
        """
        Get a description of the available action space.
        
        Args:
            preferred_method: 'test_id', 'selector', or None (show both)
        """
        return self._registry.get_action_space_description(preferred_method)
    
    def get_operation_categories(self) -> List[str]:
        """Get list of available operation categories."""
        categories = set()
        for op_info in self.get_operation_info().values():
            if 'category' in op_info:
                categories.add(op_info['category'])
        return sorted(list(categories))
    
    def get_operations_summary(self) -> Dict[str, Any]:
        """Get a summary of all operations and categories."""
        operations = self.list_operations()
        categories = self.get_operation_categories()
        
        summary = {
            'total_operations': len(operations),
            'categories': categories,
            'operations_by_category': {}
        }
        
        for category in categories:
            summary['operations_by_category'][category] = self.get_operations_by_category(category)
        
        return summary
    
    def validate_operation_params(self, operation_name: str, **kwargs) -> bool:
        """Validate parameters for a specific operation."""
        operation_class = self.get_operation(operation_name)
        if not operation_class:
            return False
        
        operation = operation_class()
        return operation.validate_params(**kwargs)
    
    def clear_registry(self) -> None:
        """Clear the operation registry."""
        self._registry.clear()
        self._auto_registered = False
        self.logger.info("Operation registry cleared")
    

