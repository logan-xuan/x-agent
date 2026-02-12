from typing import Dict, Any, Union
import json
import re
from pydantic import BaseModel, ValidationError, create_model
from jsonschema import validate, ValidationError as SchemaValidationError
import jsonschema


class StructuredOutputValidator:
    """
    Validates structured output from LLMs according to defined schemas.
    Supports both Pydantic and JSON schema validation.
    """

    def __init__(self):
        pass

    def validate_with_pydantic(self, output: Union[str, Dict[str, Any]], model_class: BaseModel) -> Dict[str, Any]:
        """
        Validate output using a Pydantic model.

        Args:
            output: Output to validate (string or dictionary)
            model_class: Pydantic model class to validate against

        Returns:
            Dictionary with validation result and data
        """
        try:
            # Convert string output to dict if necessary
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    return {
                        "valid": False,
                        "error": "Output is not valid JSON",
                        "data": output
                    }

            # Validate using Pydantic
            validated_data = model_class(**output)
            return {
                "valid": True,
                "data": validated_data.model_dump(),
                "error": None
            }

        except ValidationError as e:
            return {
                "valid": False,
                "error": str(e),
                "data": output
            }

    def validate_with_json_schema(self, output: Union[str, Dict[str, Any]], schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate output using a JSON schema.

        Args:
            output: Output to validate (string or dictionary)
            schema: JSON schema to validate against

        Returns:
            Dictionary with validation result and data
        """
        try:
            # Convert string output to dict if necessary
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    return {
                        "valid": False,
                        "error": "Output is not valid JSON",
                        "data": output
                    }

            # Validate using JSON schema
            validate(instance=output, schema=schema)
            return {
                "valid": True,
                "data": output,
                "error": None
            }

        except SchemaValidationError as e:
            return {
                "valid": False,
                "error": str(e),
                "data": output
            }

    def validate_mcp_format(self, output: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate that output follows MCP (Model Control Protocol) format conventions.

        Args:
            output: Output to validate

        Returns:
            Dictionary with validation result
        """
        try:
            # Convert string output to dict if necessary
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    return {
                        "valid": False,
                        "error": "Output is not valid JSON",
                        "data": output
                    }

            # Check if it follows MCP conventions
            if isinstance(output, dict):
                # Check for MCP tool call format
                if "type" in output and output["type"] == "tool-call":
                    required_fields = ["name", "arguments"]
                    for field in required_fields:
                        if field not in output:
                            return {
                                "valid": False,
                                "error": f"MCP tool-call missing required field: {field}",
                                "data": output
                            }
                    return {
                        "valid": True,
                        "data": output,
                        "error": None
                    }

                # Check for MCP response format
                elif "type" in output and output["type"] == "tool-response":
                    required_fields = ["call_id", "content"]
                    for field in required_fields:
                        if field not in output:
                            return {
                                "valid": False,
                                "error": f"MCP tool-response missing required field: {field}",
                                "data": output
                            }
                    return {
                        "valid": True,
                        "data": output,
                        "error": None
                    }

                # Check for MCP tools format
                elif "tools" in output and isinstance(output["tools"], list):
                    # Validate each tool in the list
                    for i, tool in enumerate(output["tools"]):
                        if not isinstance(tool, dict):
                            return {
                                "valid": False,
                                "error": f"Tool at index {i} is not a dictionary",
                                "data": output
                            }

                        if "name" not in tool or "description" not in tool:
                            return {
                                "valid": False,
                                "error": f"Tool at index {i} missing required fields (name, description)",
                                "data": output
                            }

                    return {
                        "valid": True,
                        "data": output,
                        "error": None
                    }

            return {
                "valid": False,
                "error": "Output does not conform to known MCP formats",
                "data": output
            }

        except Exception as e:
            return {
                "valid": False,
                "error": f"Error validating MCP format: {str(e)}",
                "data": output
            }

    def create_dynamic_model(self, schema_dict: Dict[str, Any], model_name: str = "DynamicModel") -> BaseModel:
        """
        Create a Pydantic model dynamically from a schema dictionary.

        Args:
            schema_dict: Schema definition
            model_name: Name for the new model

        Returns:
            Dynamic Pydantic model class
        """
        # Extract field definitions from the schema
        properties = schema_dict.get("properties", {})
        required_fields = schema_dict.get("required", [])

        # Create field definitions for Pydantic
        field_definitions = {}
        for field_name, field_spec in properties.items():
            # Map JSON schema types to Python types
            field_type = self._map_json_type_to_python(field_spec.get("type"))
            is_optional = field_name not in required_fields

            if is_optional:
                field_definitions[field_name] = (field_type, None)
            else:
                field_definitions[field_name] = (field_type, ...)

        # Create the dynamic model
        DynamicModel = create_model(model_name, **field_definitions)
        return DynamicModel

    def _map_json_type_to_python(self, json_type: str):
        """
        Map JSON schema types to Python types.

        Args:
            json_type: JSON schema type string

        Returns:
            Corresponding Python type
        """
        type_mapping = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict
        }

        return type_mapping.get(json_type, str)

    def validate_function_call_format(self, output: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate that output follows function calling format.

        Args:
            output: Output to validate

        Returns:
            Dictionary with validation result
        """
        try:
            # Convert string output to dict if necessary
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    return {
                        "valid": False,
                        "error": "Output is not valid JSON",
                        "data": output
                    }

            # Check for function calling format
            if isinstance(output, dict):
                # Check if it has function call structure
                if "name" in output and "arguments" in output:
                    # arguments should be a dict or parseable as JSON
                    if not isinstance(output["arguments"], dict):
                        try:
                            json.loads(output["arguments"])
                        except (json.JSONDecodeError, TypeError):
                            return {
                                "valid": False,
                                "error": "Arguments in function call are not a valid object or JSON string",
                                "data": output
                            }

                    return {
                        "valid": True,
                        "data": output,
                        "error": None
                    }

                # Check if it's a list of function calls
                elif isinstance(output, list):
                    for i, item in enumerate(output):
                        if not (isinstance(item, dict) and "name" in item and "arguments" in item):
                            return {
                                "valid": False,
                                "error": f"Item at index {i} is not a valid function call",
                                "data": output
                            }

                    return {
                        "valid": True,
                        "data": output,
                        "error": None
                    }

            return {
                "valid": False,
                "error": "Output does not conform to function calling format",
                "data": output
            }

        except Exception as e:
            return {
                "valid": False,
                "error": f"Error validating function call format: {str(e)}",
                "data": output
            }

    def validate_all_formats(self, output: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate output against all supported formats.

        Args:
            output: Output to validate

        Returns:
            Dictionary with validation results for all formats
        """
        results = {
            "mcp_valid": self.validate_mcp_format(output),
            "function_call_valid": self.validate_function_call_format(output)
        }

        # Determine if any format is valid
        overall_valid = (
            results["mcp_valid"]["valid"] or
            results["function_call_valid"]["valid"]
        )

        return {
            "overall_valid": overall_valid,
            "validation_results": results,
            "data": output
        }