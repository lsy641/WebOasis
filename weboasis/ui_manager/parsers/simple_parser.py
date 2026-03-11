#!/usr/bin/env python3
"""
Simple Parser for Response Formats

This parser is designed to handle different response formats that prompt engineers
design for their models, such as:
- Function call format: fill('29', 'c3c4')
- JSON format: {"action": "fill", "params": ["29", "c3c4"]}
- Natural language: "Fill the field with '29' and 'c3c4'"
"""

import re
import json
import ast
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedAction:
    """Represents a parsed action from a model response."""
    operation_name: str
    parameters: Dict[str, Any]
    confidence: float = 1.0
    raw_response: str = ""
    parser_type: str = "unknown"


class SimpleParser:
    """
    A simple parser that handles common response formats.
    
    Focuses on the format of the response, not the model that generated it.
    Ready to use without explicit initialization.
    """

    # Precompiled patterns as class attributes (no instance initialization needed)
    _function_call_pattern = re.compile(r'(\w+)\s*\(([^)]*)\)')
    _json_pattern = re.compile(r'\{[^}]*\}')
    _quoted_string_pattern = re.compile(r"'([^']*)'|\"([^\"]*)\"")

    @classmethod
    def parse(cls, response: str, available_operations: List[str]) -> Optional[ParsedAction]:
        """
        Parse a response string into a ParsedAction.
        
        Args:
            response: The raw response string (e.g., "fill('29', 'c3c4')")
            available_operations: List of available operation names
            
        Returns:
            ParsedAction if parsing succeeds, None otherwise
        """
        response = response.strip()
        
        # Try function call format first (e.g., "fill('29', 'c3c4')")
        parsed = cls._parse_function_call(response, available_operations)
        if parsed:
            return parsed
        
        # Try JSON format
        parsed = cls._parse_json(response, available_operations)
        if parsed:
            return parsed
        
        # Try natural language format
        parsed = cls._parse_natural_language(response, available_operations)
        if parsed:
            return parsed
        
        return None
    
    @classmethod
    def _clean_markdown(cls, response: str) -> str:
        """
        Clean markdown formatting from response to extract function calls.
        Removes markdown code blocks and inline code formatting.
        """
        import re
        
        # Remove markdown code blocks: ```code``` or ```language code```
        # Simple approach: just extract content between ``` ```
        cleaned = re.sub(r'```([^`]+)```', r'\1', response)
        
        # Remove inline code: `code`
        cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
        
        # Remove extra whitespace and newlines, but preserve single spaces
        cleaned = re.sub(r'\n+', ' ', cleaned)
        cleaned = re.sub(r' +', ' ', cleaned).strip()
        
        return cleaned
    
    @classmethod
    def _parse_function_call(cls, response: str, available_operations: List[str]) -> Optional[ParsedAction]:
        """
        Parse function call format: operation(param1, param2, ...)
        
        Examples:
        - fill('29', 'c3c4')
        - click('submit')
        - type_text('hello world')
        - type(test_id='23', text='dfdeef(dffgfd\n)')
        """
        # Clean response by removing markdown formatting
        cleaned_response = cls._clean_markdown(response)
        
        # Find operation name (word before first parenthesis anywhere in the string)
        operation_match = re.search(r'(\w+)\s*\(', cleaned_response)
        if not operation_match:
            return None
        
        operation_name = operation_match.group(1).lower()  # Normalize to lowercase
        
        # Check if operation is available (also normalize available_operations to lowercase for comparison)
        # Create a mapping from lowercase to original case
        operation_map = {op.lower(): op for op in available_operations}
        if operation_name not in operation_map:
            logger.warning(f"Operation '{operation_name}' not found in available operations: {available_operations}")
            return None
        
        # Use the original case from available_operations
        operation_name = operation_map[operation_name]
        # Find the opening parenthesis (should be right after the operation name)
        open_paren = cleaned_response.find('(', operation_match.start())
        if open_paren == -1:
            return None
        # Find the matching closing parenthesis by counting parentheses
        # But we need to be smart about quotes to handle text parameters with parentheses
        paren_count = 0
        close_paren = -1
        in_quotes = False
        quote_char = None
        
        for i, char in enumerate(cleaned_response[open_paren:], open_paren):
            # Handle quote transitions
            if char in "'\"" and not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
            # Only count parentheses when not inside quotes
            elif not in_quotes:
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        close_paren = i
                        break
        
        if close_paren == -1:
            logger.error("Could not find matching closing parenthesis")
            return None
        
        # Extract the parameters string
        params_str = cleaned_response[open_paren + 1:close_paren]
        
        # Extract parameters using ast.literal_eval for robust parsing
        parameters = cls._extract_function_parameters(params_str)
        
        return ParsedAction(
            operation_name=operation_name,
            parameters=parameters,
            raw_response=response,
            parser_type="function_call",
            confidence=1.0
        )
    
    @classmethod
    def _extract_from_markdown(cls, response: str, available_operations: List[str]) -> Optional[ParsedAction]:
        """
        Extract function calls from markdown code blocks.
        
        Examples:
        - ```scroll(delta_x=0, delta_y=300)```
        - `click(test_id="123")`
        - ```json
          {"action": "scroll", "params": {"delta_x": 0, "delta_y": 300}}
          ```
        """
        # Look for markdown code blocks with function calls
        import re
        
        # Pattern for markdown code blocks: ```code``` or `code`
        markdown_patterns = [
            r'```(\w+)?\s*([^`]+)```',  # ```code``` or ```language code```
            r'`([^`]+)`',                # `code`
        ]
        
        for pattern in markdown_patterns:
            matches = re.findall(pattern, response)
            for match in matches:
                if len(match) == 2:  # ```language code``` format
                    code_content = match[1].strip()
                else:  # `code` format
                    code_content = match[0].strip()
                
                # Try to parse the code content as a function call
                parsed = cls._parse_function_call(code_content, available_operations)
                if parsed:
                    logger.debug(f"Extracted function call from markdown: {code_content}")
                    return parsed
        
        return None
    
    @classmethod
    def _extract_function_parameters(cls, params_str: str) -> Dict[str, Any]:
        """
        Extract parameters from function call string using ast.literal_eval for safe parsing.
        This handles all the complex cases with escaped characters, mixed quotes, etc.
        """
        parameters = {}
        
        try:
            # Convert parameter string from "key=value" format to "key": value format
            # This makes it compatible with ast.literal_eval
            converted_params = cls._convert_params_to_python_syntax(params_str)
            logger.debug(f"Converted params: {converted_params}")
            
            # Try to parse the converted parameter string as a Python literal
            parsed_params = ast.literal_eval(f"{{{converted_params}}}")
            if isinstance(parsed_params, dict):
                logger.debug(f"ast.literal_eval succeeded: {parsed_params}")
                return parsed_params
        except (ValueError, SyntaxError) as e:
            logger.warning(f"ast.literal_eval failed for params_str: {params_str}, error: {e}")
        
        # Fallback to manual parsing if ast.literal_eval fails
        logger.warning(f"Falling back to manual parsing for: {params_str}")
        return cls._extract_function_parameters_manual(params_str)
    
    @classmethod
    def _extract_function_parameters_manual(cls, params_str: str) -> Dict[str, Any]:
        """
        Manual fallback parameter extraction when ast.literal_eval fails.
        This handles edge cases that ast.literal_eval can't parse.
        """
        parameters = {}
        
        # Handle text parameter specially since it can contain commas and parentheses
        if 'text=' in params_str:
            
            # Use regex to extract text parameter more reliably
            # Pattern to match text parameter with any content (including parentheses, quotes, etc.)
            text_pattern = r'text\s*=\s*["\']([^"\']*(?:\([^"\']*\)[^"\']*)*)["\']'
            text_match = re.search(text_pattern, params_str)
            
            if text_match:
                text_value = text_match.group(1)
                parameters['text'] = text_value
                logger.debug(f"Successfully extracted text parameter: {text_value[:100]}...")
                
                # Remove the text parameter from params_str to avoid double processing
                text_start = text_match.start()
                remaining_params = params_str[:text_start].strip()
                if remaining_params.endswith(','):
                    remaining_params = remaining_params[:-1].strip()
                if remaining_params:
                    # Parse remaining parameters
                    remaining_parameters = cls._parse_remaining_parameters(remaining_params)
                    parameters.update(remaining_parameters)
            else:
                logger.error("Could not extract text parameter with regex")
        
        # Split remaining parameters by comma, handling quoted strings
        parts = []
        current_part = ""
        in_quotes = False
        quote_char = None
        
        for char in params_str:
            if char in "'\"" and not in_quotes:
                in_quotes = True
                quote_char = char
                current_part += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current_part += char
            elif char == ',' and not in_quotes:
                parts.append(current_part.strip())
                current_part = ""
            else:
                current_part += char
        
        if current_part.strip():
            parts.append(current_part.strip())
        
        # Process each part
        for i, part in enumerate(parts):
            part = part.strip()
            
            # Check if it's a named parameter (key=value)
            if '=' in part and not part.startswith("'") and not part.startswith('"'):
                key, value = part.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes from value if present
                if (value.startswith("'") and value.endswith("'")) or \
                   (value.startswith('"') and value.endswith('"')):
                    value = value[1:-1]
                
                # Convert value to appropriate type
                converted_value = cls._convert_parameter_value(key, value)
                parameters[key] = converted_value
            else:
                # Positional parameter
                # Remove quotes if present
                if (part.startswith("'") and part.endswith("'")) or \
                   (part.startswith('"') and part.endswith('"')):
                    part = part[1:-1]
                
                parameters[f"arg_{i}"] = part
        
        return parameters
    
    @classmethod
    def _parse_remaining_parameters(cls, params_str: str) -> Dict[str, Any]:
        """
        Parse remaining parameters after text parameter extraction.
        """
        parameters = {}
        
        # Split by comma, handling quoted strings
        parts = []
        current_part = ""
        in_quotes = False
        quote_char = None
        
        for char in params_str:
            if char in "'\"" and not in_quotes:
                in_quotes = True
                quote_char = char
                current_part += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current_part += char
            elif char == ',' and not in_quotes:
                parts.append(current_part.strip())
                current_part = ""
            else:
                current_part += char
        
        if current_part.strip():
            parts.append(current_part.strip())
        
        # Process each part
        for i, part in enumerate(parts):
            part = part.strip()
            
            # Check if it's a named parameter (key=value)
            if '=' in part and not part.startswith("'") and not part.startswith('"'):
                key, value = part.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes from value if present
                if (value.startswith("'") and value.endswith("'")) or \
                   (value.startswith('"') and value.endswith('"')):
                    value = value[1:-1]
                
                # Convert value to appropriate type
                converted_value = cls._convert_parameter_value(key, value)
                parameters[key] = converted_value
            else:
                # Positional parameter
                # Remove quotes if present
                if (part.startswith("'") and part.endswith("'")) or \
                   (part.startswith('"') and part.endswith('"')):
                    part = part[1:-1]
                
                parameters[f"arg_{i}"] = part
        
        return parameters
    
    @classmethod
    def _convert_params_to_python_syntax(cls, params_str: str) -> str:
        """
        Convert parameter string from "key=value" format to "key": value format.
        This makes it compatible with ast.literal_eval.
        
        Examples:
        - Input:  'test_id="236", value="hello"'
        - Output: '"test_id": "236", "value": "hello"'
        """
        if not params_str.strip():
            return ""
        
        # Split by comma, handling quoted strings
        parts = []
        current_part = ""
        in_quotes = False
        quote_char = None
        
        for char in params_str:
            if char in "'\"" and not in_quotes:
                in_quotes = True
                quote_char = char
                current_part += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current_part += char
            elif char == ',' and not in_quotes:
                parts.append(current_part.strip())
                current_part = ""
            else:
                current_part += char
        
        if current_part.strip():
            parts.append(current_part.strip())
        
        # Convert each part from "key=value" to '"key": value'
        converted_parts = []
        for part in parts:
            part = part.strip()
            if '=' in part and not part.startswith("'") and not part.startswith('"'):
                # Named parameter: key=value
                key, value = part.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Convert to Python syntax: "key": value
                converted_part = f'"{key}": {value}'
                converted_parts.append(converted_part)
            else:
                # Positional parameter: just the value
                converted_parts.append(part)
        
        return ", ".join(converted_parts)
    
    @classmethod
    def _convert_parameter_value(cls, param_name: str, value: str) -> Any:
        """
        Convert parameter value to appropriate type (from registry.py logic).
        
        Args:
            param_name: Name of the parameter
            value: String value to convert
            
        Returns:
            Converted value with appropriate type
        """
        try:
            # Convert numeric values
            if param_name in ['x', 'y', 'delta_x', 'delta_y']:
                return float(value)
            elif param_name in ['timeout']:
                return int(value)
            else:
                return value
        except (ValueError, TypeError):
            # Return original value if conversion fails
            return value
    
    @classmethod
    def _parse_json(cls, response: str, available_operations: List[str]) -> Optional[ParsedAction]:
        """
        Parse JSON format: {"action": "fill", "params": ["29", "c3c4"]}
        """
        try:
            # Find JSON in the response
            json_match = cls._json_pattern.search(response)
            if not json_match:
                return None
            
            json_str = json_match.group(0)
            data = json.loads(json_str)
            
            # Try different JSON formats
            operation_name = None
            
            # Format 1: {"action": "fill", "params": ["29", "c3c4"]}
            if "action" in data:
                operation_name = data["action"]
                parameters = data.get("params", {})
                if isinstance(parameters, list):
                    # Convert list to dict with arg_0, arg_1, etc.
                    parameters = {f"arg_{i}": param for i, param in enumerate(parameters)}
            
            # Format 2: {"operation": "fill", "parameters": {"text": "29", "field": "c3c4"}}
            elif "operation" in data:
                operation_name = data["operation"]
                parameters = data.get("parameters", {})
            
            # Format 3: {"fill": {"text": "29", "field": "c3c4"}}
            else:
                # Look for operation name as a key
                for key in data:
                    if key in available_operations:
                        operation_name = key
                        parameters = data[key]
                        break
            
            if operation_name and operation_name in available_operations:
                return ParsedAction(
                    operation_name=operation_name,
                    parameters=parameters,
                    raw_response=response,
                    parser_type="json",
                    confidence=1.0
                )
        
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        
        return None
    
    @classmethod
    def _parse_natural_language(cls, response: str, available_operations: List[str]) -> Optional[ParsedAction]:
        """
        Parse natural language format: "Fill the field with '29' and 'c3c4'"
        """
        response_lower = response.lower()
        
        # Look for operation keywords
        operation_keywords = {
            'click': ['click', 'press', 'tap', 'select'],
            'type_text': ['type', 'enter', 'input', 'fill', 'write'],
            'scroll': ['scroll', 'move', 'navigate'],
            'navigate': ['go to', 'visit', 'navigate', 'open']
        }
        
        for operation, keywords in operation_keywords.items():
            if operation not in available_operations:
                continue
            
            for keyword in keywords:
                if keyword in response_lower:
                    # Extract quoted strings as parameters
                    quoted_strings = cls._quoted_string_pattern.findall(response)
                    parameters = {}
                    
                    for i, (single_quote, double_quote) in enumerate(quoted_strings):
                        value = single_quote if single_quote else double_quote
                        parameters[f"arg_{i}"] = value
                    
                    if parameters:
                        return ParsedAction(
                            operation_name=operation,
                            parameters=parameters,
                            raw_response=response,
                            parser_type="natural_language",
                            confidence=0.8
                        )
        
        return None
    
    @classmethod
    def get_parser_info(cls) -> Dict[str, Any]:
        """Get information about this parser."""
        return {
            "type": "simple",
            "description": "Simple parser for common response formats",
            "supported_formats": [
                "function_call: operation(param1, param2, ...)",
                "json: {\"action\": \"operation\", \"params\": [...]}",
                "natural_language: \"Click the button\""
            ]
        }


def create_simple_parser() -> SimpleParser:
    """Create a simple parser instance (backward compatible)."""
    return SimpleParser()


# Example usage and testing
if __name__ == "__main__":
    # Test the parser with different formats
    parser = create_simple_parser()
    available_operations = ['click', 'type_text', 'fill', 'scroll', 'navigate', 'type']
    
    test_responses = [
        "fill('29', 'c3c4')",  # Function call format
        '{"action": "click", "params": ["submit"]}',  # JSON format
        'Click the "Submit" button',  # Natural language
        'type_text(text="hello world")',  # Named parameters
        'scroll(direction="down", amount=100)',  # Complex parameters
        'click(test_id="781")',  # Mixed quotes
        "click(test_id='781')",  # Single quotes
        "click(test_id=781)",  # No quotes
        "waitfornavigation(timeout=30000)",  # Numeric value
        "type(test_id='23', text='dfdeef(dffgfd\n)')",  # Newlines and parentheses
        'type(test_id="23", text="dfdeef(dffgfd\n)")',  # Mixed quotes with newlines
        "type(test_id=\"23\", text=\"dfdeef(dffgfd\\n)\")",  # Escaped newlines
        'type(test_id="23", text="df\"de\"ef(dffgfd\n)")',  # Nested quotes
        "type(test_id=\"226\", text=\"I am currently considering Robot-Assisted Laparoscopic Prostatectomy (RALP) and active surveillance as my treatment options. I would like to understand the risks and benefits associated with each option to make an informed decision. Could you please provide more details on both?\")",  # Long text with parentheses
        # User's specific test cases
        'type(test_id="236", text="I have received my PSA test results showing a PSA level of 4.4 last fall and 5.1 this summer. The biopsy indicated cancer in 4 out of 12 cores: 2 with Gleason 3+4 (grade group 2) and 2 with Gleason 3+3 (grade group 1). Perineural invasion was noted. The Decipher test score was 0.46, placing me in the intermediate risk group.")',
        "type(test_id=\"236\", text=\"I have received my PSA test results showing a PSA level of 4.4 last fall and 5.1 this summer. The biopsy indicated cancer in 4 out of 12 cores: 2 with Gleason 3+4 (grade group 2) and 2 with Gleason 3+3 (grade group 1). Perineural invasion was noted. The Decipher test score was 0.46, placing me in the intermediate risk group.\")",
    ]
    
    
    for response in test_responses:
        print(f"\n📝 Response: {response}")
        parsed = parser.parse(response, available_operations)
        
        if parsed:
            print(f"✅ Parsed: {parsed.operation_name}({parsed.parameters})")
            print(f"   Parser: {parsed.parser_type}")
            print(f"   Confidence: {parsed.confidence}")
        else:
            print("❌ Failed to parse")
    
    print(f"\n📋 Parser Info: {parser.get_parser_info()}")
