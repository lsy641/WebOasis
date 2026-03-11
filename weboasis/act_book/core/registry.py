"""
Enhanced Operation Registry
Comprehensive operation management including registration, discovery, and LLM response parsing.
"""

import re
import inspect
from typing import Dict, Type, List, Tuple, Optional, Any
from .base import Operation
import logging
logger = logging.getLogger(__name__)


class OperationRegistry:
    """Enhanced registry for managing operations and parsing LLM responses."""
    
    _operations: Dict[str, Type[Operation]] = {}
    _operation_info: Dict[str, Dict[str, Any]] = {}
    _patterns: List[Tuple[str, str, callable]] = []
    
    @classmethod
    def register(cls, operation_class: Type[Operation]) -> Type[Operation]:
        """Register an operation class and update parsing patterns."""
        cls._operations[operation_class.__name__.lower()] = operation_class
        cls._refresh_operation_info()
        cls._build_patterns()
        return operation_class
    
    @classmethod
    def unregister(cls, operation_name: str) -> bool:
        """Unregister an operation by name."""
        operation_name_lower = operation_name.lower()
        if operation_name_lower in cls._operations:
            del cls._operations[operation_name_lower]
            cls._refresh_operation_info()
            cls._build_patterns()
            return True
        return False
    
    @classmethod
    def clear(cls) -> None:
        """Clear all registered operations."""
        cls._operations.clear()
        cls._operation_info.clear()
        cls._patterns.clear()
    
    @classmethod
    def get_operation(cls, name: str) -> Type[Operation]:
        """Get an operation class by name."""
        return cls._operations.get(name.lower())
    
    @classmethod
    def get_operations(cls, names: Optional[List[str]] = None) -> Dict[str, Type[Operation]]:
        """Get operation classes by names. If names is None, returns all operations."""
        if names is None:
            return cls._operations.copy()
        
        result = {}
        for name in names:
            operation = cls._operations.get(name.lower())
            if operation:
                result[name.lower()] = operation
        return result
    
    @classmethod
    def list_operations(cls) -> List[str]:
        """List all registered operation names."""
        return list(cls._operations.keys())
    
    @classmethod
    def get_operations_by_category(cls, category: str) -> List[str]:
        """Get operations by category."""
        return [
            name for name, op_class in cls._operations.items()
            if op_class().category == category
        ]
    
    @classmethod
    def get_operation_info(cls) -> Dict[str, Dict[str, Any]]:
        """Get detailed information about all operations."""
        cls._refresh_operation_info()
        return cls._operation_info.copy()
    
    @classmethod
    def _refresh_operation_info(cls):
        """Refresh operation information and metadata."""
        cls._operation_info = {}
        
        for operation_name in cls._operations:
            operation_class = cls._operations[operation_name]
            try:
                operation_instance = operation_class()
                cls._operation_info[operation_name] = {
                    'class': operation_class,
                    'instance': operation_instance,
                    'description': operation_instance.description,
                    'category': operation_instance.category,
                    'parameters': cls._extract_parameters(operation_class)
                }
            except Exception as e:
                # Skip operations that can't be instantiated
                continue
    
    @classmethod
    def _extract_parameters(cls, operation_class) -> Dict[str, Dict[str, Any]]:
        """Extract parameter information from operation class."""
        parameters = {}
        
        execute_method = getattr(operation_class, 'execute', None)
        if execute_method:
            sig = inspect.signature(execute_method)
            
            for param_name, param in sig.parameters.items():
                if param_name not in ['self', 'automator']:
                    param_info = {
                        'type': param.annotation if param.annotation != inspect.Parameter.empty else Any,
                        'default': param.default if param.default != inspect.Parameter.empty else None,
                        'required': param.default == inspect.Parameter.empty
                    }
                    parameters[param_name] = param_info
        
        return parameters
    
    @classmethod
    def _build_patterns(cls):
        """Build regex patterns for parsing LLM responses."""
        cls._patterns = []
        
        for operation_name, info in cls._operation_info.items():
            parameters = info['parameters']
            cls._add_operation_patterns(operation_name, parameters)
    
    @classmethod
    def _add_operation_patterns(cls, operation_name: str, parameters: Dict[str, Dict[str, Any]]):
        """Add parsing patterns for a specific operation."""
        
        # Parameter type patterns
        param_patterns = {
            'test_id': r'test_id\s*=\s*["\']([^"\']+)["\']',
            'selector': r'selector\s*=\s*["\']([^"\']+)["\']',
            'value': r'value\s*=\s*["\']([^"\']+)["\']',
            'text': r'text\s*=\s*["\']([^"\']+)["\']',
            'url': r'url\s*=\s*["\']([^"\']+)["\']',
            'options': r'options\s*=\s*["\']([^"\']+)["\']',
            'key': r'key\s*=\s*["\']([^"\']+)["\']',
            'x': r'x\s*=\s*([^,)]+)',
            'y': r'y\s*=\s*([^,)]+)',
            'delta_x': r'delta_x\s*=\s*([^,)]+)',
            'delta_y': r'delta_y\s*=\s*([^,)]+)',
            'timeout': r'timeout\s*=\s*([^,)]+)',
            'button': r'button\s*=\s*["\']([^"\']+)["\']',
            'modifiers': r'modifiers\s*=\s*\[([^\]]+)\]',
        }
        
        param_names = list(parameters.keys())
        
        # Handle operations with no parameters
        if not param_names:
            pattern = rf'{operation_name}\s*\(\s*\)'
            cls._patterns.append((pattern, operation_name, lambda groups: {}))
            return
        
        # Generate patterns for common parameter combinations
        common_combinations = cls._get_common_combinations(param_names)
        
        for combo in common_combinations:
            pattern_parts = []
            
            for param_name in combo:
                if param_name in param_patterns:
                    pattern_parts.append(param_patterns[param_name])
            
            if pattern_parts:
                pattern = rf'{operation_name}\s*\(\s*' + r',\s*'.join(pattern_parts) + r'\s*\)'
                
                def make_extractor(combo):
                    def extractor(groups):
                        params = {}
                        for i, param_name in enumerate(combo):
                            if i < len(groups):
                                value = groups[i]
                                # Convert numeric values
                                if param_name in ['x', 'y', 'delta_x', 'delta_y']:
                                    try:
                                        params[param_name] = float(value)
                                    except ValueError:
                                        params[param_name] = value
                                elif param_name == 'timeout':
                                    try:
                                        params[param_name] = int(value)
                                    except ValueError:
                                        params[param_name] = value
                                else:
                                    params[param_name] = value
                        return params
                    return extractor
                
                cls._patterns.append((pattern, operation_name, make_extractor(combo)))
    
    @classmethod
    def _get_common_combinations(cls, param_names: List[str]) -> List[List[str]]:
        """Get common parameter combinations for operations."""
        combinations = []
        
        # Common patterns for different operation types
        if 'test_id' in param_names and 'selector' in param_names:
            combinations.extend([
                ['test_id'], ['selector'],
                ['test_id', 'value'], ['selector', 'value'],
                ['test_id', 'text'], ['selector', 'text'],
                ['test_id', 'options'], ['selector', 'options'],
                ['test_id', 'key'], ['selector', 'key'],
            ])
        
        # Coordinate-based operations
        if 'x' in param_names and 'y' in param_names:
            combinations.append(['x', 'y'])
        
        # Scroll operations
        if 'delta_x' in param_names and 'delta_y' in param_names:
            combinations.append(['delta_x', 'delta_y'])
        
        # Navigation operations
        if 'url' in param_names:
            combinations.append(['url'])
        
        # Text input operations
        if 'text' in param_names:
            combinations.append(['text'])
        
        # Key operations
        if 'key' in param_names:
            combinations.append(['key'])
        
        # Timeout operations
        if 'timeout' in param_names:
            combinations.append(['timeout'])
        
        # Button operations
        if 'button' in param_names:
            combinations.append(['button'])
        
        # Remove duplicates and sort by length
        unique_combinations = []
        for combo in combinations:
            if combo not in unique_combinations:
                unique_combinations.append(combo)
        
        return sorted(unique_combinations, key=len)
    
    @classmethod
    def parse_action(cls, response_text: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Parse action from LLM response using registered operations.
        
        Args:
            response_text: The LLM response text to parse
            
        Returns:
            Tuple of (operation_name, parameters_dict) or (None, None) if parsing fails
        """
        cls._refresh_operation_info()
        cls._build_patterns()
        
        response_text = response_text.strip()
        
        for pattern, operation_name, param_extractor in cls._patterns:
            match = re.search(pattern, response_text)
            if match:
                try:
                    parameters = param_extractor(match.groups())
                    return operation_name, parameters
                except (ValueError, TypeError) as e:
                    continue
        
        return None, None
    
    @classmethod
    def parse_multiple_actions(cls, response_text: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Parse multiple actions from a single response.
        
        Args:
            response_text: The LLM response text to parse
            
        Returns:
            List of (operation_name, parameters_dict) tuples
        """
        actions = []
        lines = response_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if line:
                operation_name, parameters = cls.parse_action(line)
                if operation_name and parameters:
                    actions.append((operation_name, parameters))
        
        return actions
    
    @classmethod
    def get_action_space_description(cls, preferred_method: str = None) -> str:
        """
        Get a formatted description of available actions for LLM prompts.
        
        Args:
            preferred_method: 'test_id', 'selector', or None (show both)
        
        Returns:
            Formatted string describing all available operations
        """
        cls._refresh_operation_info()
        
        description_parts = []
        description_parts.append(f"Available operations: {', '.join(cls._operation_info.keys())}")
        description_parts.append("")
        description_parts.append("Action format examples:")
        
        # Group operations by category
        categories = {}
        for op_name, info in cls._operation_info.items():
            category = info['category']
            if category not in categories:
                categories[category] = []
            categories[category].append((op_name, info))
        
        # Generate examples for each category
        for category, operations in categories.items():
            description_parts.append(f"\n{category.replace('_', ' ').title()}:")
            
            for op_name, info in operations:
                examples = cls._generate_examples(op_name, info['parameters'], preferred_method)
                for example in examples:
                    description_parts.append(f"- {example}")
        
        return "\n".join(description_parts)
    
    @classmethod
    def _generate_examples(cls, operation_name: str, parameters: Dict[str, Dict[str, Any]], preferred_method: str = None) -> List[str]:
        """Generate example usage strings for an operation."""
        examples = []

        # Special-case richer examples for scroll, where delta_x/delta_y are required
        # and test_id/selector/x/y are optional variants
        if operation_name.lower() == 'scroll':
            # General page scroll (required deltas)
            examples.append('scroll(delta_x=0, delta_y=300) - general page scroll')
            # From absolute viewport position
            examples.append('scroll(x=500, y=300, delta_x=0, delta_y=600) - scroll from absolute position')
            # From element position (test_id or selector), honor preferred_method
            if preferred_method == 'test_id':
                examples.append('scroll(test_id="123.45", delta_y=600) - scroll from element by test_id')
            elif preferred_method == 'selector':
                examples.append('scroll(selector="#panel", delta_x=-200) - scroll from element by selector')
            else:
                examples.append('scroll(test_id="123.45", delta_y=600) - scroll from element by test_id')
                examples.append('scroll(selector="#panel", delta_x=-200) - scroll from element by selector')
            return examples
        # Common parameter combinations
        if 'test_id' in parameters and 'selector' in parameters:
            if preferred_method == 'test_id':
                # Only show test_id examples
                if 'value' in parameters:
                    examples.append(f'{operation_name}(test_id="123.45", value="text") - {operation_name} by test_id')
                elif 'text' in parameters:
                    examples.append(f'{operation_name}(test_id="123.45", text="text") - {operation_name} by test_id')
                elif 'options' in parameters:
                    examples.append(f'{operation_name}(test_id="123.45", options="option1") - {operation_name} by test_id')
                elif 'key' in parameters:
                    examples.append(f'{operation_name}(test_id="123.45", key="Enter") - {operation_name} by test_id')
                else:
                    examples.append(f'{operation_name}(test_id="123.45") - {operation_name} by test_id')
            
            elif preferred_method == 'selector':
                # Only show selector examples
                if 'value' in parameters:
                    examples.append(f'{operation_name}(selector="#input", value="text") - {operation_name} by selector')
                elif 'text' in parameters:
                    examples.append(f'{operation_name}(selector="#input", text="text") - {operation_name} by selector')
                elif 'options' in parameters:
                    examples.append(f'{operation_name}(selector="#select", options="option1") - {operation_name} by selector')
                elif 'key' in parameters:
                    examples.append(f'{operation_name}(selector="#input", key="Enter") - {operation_name} by selector')
                else:
                    examples.append(f'{operation_name}(selector="#button") - {operation_name} by selector')
            
            else:
                # Show both (default behavior)
                if 'value' in parameters:
                    examples.append(f'{operation_name}(test_id="123.45", value="text") - {operation_name} by test_id')
                    examples.append(f'{operation_name}(selector="#input", value="text") - {operation_name} by selector')
                elif 'text' in parameters:
                    examples.append(f'{operation_name}(test_id="123.45", text="text") - {operation_name} by test_id')
                    examples.append(f'{operation_name}(selector="#input", text="text") - {operation_name} by selector')
                elif 'options' in parameters:
                    examples.append(f'{operation_name}(test_id="123.45", options="option1") - {operation_name} by test_id')
                    examples.append(f'{operation_name}(selector="#select", options="option1") - {operation_name} by selector')
                elif 'key' in parameters:
                    examples.append(f'{operation_name}(test_id="123.45", key="Enter") - {operation_name} by test_id')
                    examples.append(f'{operation_name}(selector="#input", key="Enter") - {operation_name} by selector')
                else:
                    examples.append(f'{operation_name}(test_id="123.45") - {operation_name} by test_id')
                    examples.append(f'{operation_name}(selector="#button") - {operation_name} by selector')
        
        elif 'url' in parameters:
            examples.append(f'{operation_name}(url="https://example.com") - {operation_name}')
        
        elif 'x' in parameters and 'y' in parameters:
            examples.append(f'{operation_name}(x=100, y=200) - {operation_name}')
        
        elif 'delta_x' in parameters and 'delta_y' in parameters:
            examples.append(f'{operation_name}(delta_x=0, delta_y=300) - {operation_name}')
        
        elif 'text' in parameters:
            examples.append(f'{operation_name}(text="text") - {operation_name}')
        
        elif 'key' in parameters:
            examples.append(f'{operation_name}(key="Enter") - {operation_name}')
        
        elif 'timeout' in parameters:
            examples.append(f'{operation_name}(timeout=30000) - {operation_name}')
        
        elif not parameters:
            examples.append(f'{operation_name}() - {operation_name}')
        
        return examples
    
def register_operation(cls: Type[Operation]) -> Type[Operation]:
    """Decorator for easy operation registration."""
    return OperationRegistry.register(cls) 