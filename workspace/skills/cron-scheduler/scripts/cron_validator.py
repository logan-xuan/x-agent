#!/usr/bin/env python3
"""
Cron Expression Validator
Validates cron expressions according to standard cron format
"""

import re
from typing import List, Tuple

def validate_cron_expression(expression: str) -> Tuple[bool, str]:
    """
    Validate a cron expression against standard cron format
    
    Args:
        expression: Cron expression string (e.g. "0 9 * * *")
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Split the expression into components
    parts = expression.strip().split()
    
    if len(parts) != 5:
        return False, f"Cron expression must have 5 fields, got {len(parts)}"
    
    minute, hour, day, month, weekday = parts
    
    # Define validation patterns
    field_patterns = [
        (minute, "Minute", 0, 59),
        (hour, "Hour", 0, 23),
        (day, "Day of Month", 1, 31),
        (month, "Month", 1, 12),
        (weekday, "Day of Week", 0, 7)  # 0 and 7 both represent Sunday
    ]
    
    for value, field_name, min_val, max_val in field_patterns:
        is_valid, msg = _validate_field(value, field_name, min_val, max_val)
        if not is_valid:
            return False, msg
    
    return True, "Valid cron expression"

def _validate_field(value: str, field_name: str, min_val: int, max_val: int) -> Tuple[bool, str]:
    """Validate individual cron field"""
    # Handle special characters
    if value in ['*', '?']:
        return True, ""
    
    # Handle step values (e.g., */5, 0-10/2)
    if '/' in value:
        if '-' in value:
            # Range with step (e.g., 0-10/2)
            range_part, step_part = value.split('/')
            if not step_part.isdigit():
                return False, f"{field_name}: Invalid step value '{step_part}'"
            
            step = int(step_part)
            if step <= 0:
                return False, f"{field_name}: Step value must be positive"
                
            if '-' not in range_part:
                return False, f"{field_name}: Invalid range format"
                
            start_str, end_str = range_part.split('-')
            if not start_str.isdigit() and start_str != '*':
                return False, f"{field_name}: Invalid range start '{start_str}'"
            if not end_str.isdigit():
                return False, f"{field_name}: Invalid range end '{end_str}'"
                
            if start_str == '*':
                start = min_val
            else:
                start = int(start_str)
            end = int(end_str)
            
            if start < min_val or end > max_val or start > end:
                return False, f"{field_name}: Range {start}-{end} is invalid (valid range: {min_val}-{max_val})"
        else:
            # Simple step (e.g., */5)
            base, step_str = value.split('/')
            if base != '*':
                return False, f"{field_name}: Invalid step format, expected */N"
            if not step_str.isdigit():
                return False, f"{field_name}: Invalid step value '{step_str}'"
    
    # Handle lists (e.g., 1,2,3 or 1,5,10)
    elif ',' in value:
        items = value.split(',')
        for item in items:
            is_valid, msg = _validate_single_value(item, field_name, min_val, max_val)
            if not is_valid:
                return False, msg
    
    # Handle ranges (e.g., 1-5)
    elif '-' in value:
        range_parts = value.split('-')
        if len(range_parts) != 2:
            return False, f"{field_name}: Invalid range format"
        
        start_str, end_str = range_parts
        if not start_str.isdigit() or not end_str.isdigit():
            return False, f"{field_name}: Range values must be numeric"
        
        start, end = int(start_str), int(end_str)
        if start < min_val or end > max_val or start > end:
            return False, f"{field_name}: Range {start}-{end} is invalid (valid range: {min_val}-{max_val})"
    
    # Handle single values
    else:
        return _validate_single_value(value, field_name, min_val, max_val)
    
    return True, ""

def _validate_single_value(value: str, field_name: str, min_val: int, max_val: int) -> Tuple[bool, str]:
    """Validate a single cron field value"""
    # Check if it's a valid alias (for months and weekdays)
    month_aliases = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    
    weekday_aliases = {
        'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6
    }
    
    if value.upper() in month_aliases or value.upper() in weekday_aliases:
        return True, ""
    
    if not value.isdigit():
        return False, f"{field_name}: Invalid value '{value}', must be numeric or valid alias"
    
    num_value = int(value)
    if num_value < min_val or num_value > max_val:
        return False, f"{field_name}: Value {num_value} is outside valid range ({min_val}-{max_val})"
    
    return True, ""

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python cron_validator.py '<cron_expression>'")
        sys.exit(1)
    
    expr = sys.argv[1]
    is_valid, message = validate_cron_expression(expr)
    
    if is_valid:
        print(f"✓ Valid: {expr}")
        sys.exit(0)
    else:
        print(f"✗ Invalid: {expr}")
        print(f"Error: {message}")
        sys.exit(1)