#!/usr/bin/env python3
"""
Cron Expression Validator
Validates cron expressions and calculates next run times
"""

import re
from datetime import datetime
from croniter import croniter


class CronValidator:
    def __init__(self):
        pass

    def validate_basic_syntax(self, cron_expr):
        """Validate basic cron expression syntax"""
        # Remove @ shortcuts and validate standard format
        if cron_expr.startswith('@'):
            return self.validate_at_shortcut(cron_expr)
        
        parts = cron_expr.split()
        if len(parts) != 5:
            return False, f"Invalid number of parts: {len(parts)}, expected 5"
        
        for i, part in enumerate(parts):
            if not self.validate_part(part, i):
                return False, f"Invalid format in position {i+1}: {part}"
        
        return True, "Valid cron expression"

    def validate_at_shortcut(self, expr):
        """Validate @ shortcut expressions"""
        valid_shortcuts = ['@yearly', '@annually', '@monthly', '@weekly', '@daily', '@midnight', '@hourly']
        if expr.lower() in valid_shortcuts:
            return True, "Valid @ shortcut"
        else:
            return False, f"Invalid @ shortcut: {expr}"

    def validate_part(self, part, position):
        """Validate individual cron expression part"""
        if not part:
            return False
        
        # Handle special characters
        if part == '*':
            return True
        if part.isdigit():
            return self.validate_range(int(part), position)
        
        # Handle ranges and steps
        if '-' in part or '/' in part:
            if '/' in part:
                # Handle step values (e.g., */5, 10-20/2)
                range_part, step = part.split('/')
                if not step.isdigit():
                    return False
                step_val = int(step)
                if step_val <= 0:
                    return False
            
                if range_part == '*':
                    # Pattern like */5
                    return True
                elif '-' in range_part:
                    # Pattern like 10-20/2
                    start, end = range_part.split('-')
                    if not (start.isdigit() and end.isdigit()):
                        return False
                    start, end = int(start), int(end)
                    if start > end:
                        return False
                    return self.validate_range(start, position) and self.validate_range(end, position)
                else:
                    # Invalid pattern
                    return False
            else:
                # Just a range like 10-20
                start, end = part.split('-')
                if not (start.isdigit() and end.isdigit()):
                    return False
                start, end = int(start), int(end)
                if start > end:
                    return False
                return self.validate_range(start, position) and self.validate_range(end, position)
        
        # Handle comma-separated lists
        if ',' in part:
            items = part.split(',')
            for item in items:
                if item.isdigit():
                    if not self.validate_range(int(item), position):
                        return False
                elif '-' in item:
                    start, end = item.split('-')
                    if not (start.isdigit() and end.isdigit()):
                        return False
                    start, end = int(start), int(end)
                    if start > end:
                        return False
                    if not (self.validate_range(start, position) and self.validate_range(end, position)):
                        return False
                else:
                    return False
            return True
        
        # Simple digit check
        if part.isdigit():
            return self.validate_range(int(part), position)
        
        return False

    def validate_range(self, value, position):
        """Validate value against allowed range for position"""
        ranges = [
            (0, 59),    # minute
            (0, 23),    # hour
            (1, 31),    # day of month
            (1, 12),    # month
            (0, 7)      # day of week (0 and 7 are Sunday)
        ]
        
        if position < len(ranges):
            min_val, max_val = ranges[position]
            return min_val <= value <= max_val
        return False

    def validate_complete(self, cron_expr, base_date=None):
        """Perform complete validation using croniter"""
        if base_date is None:
            base_date = datetime.now()
        
        try:
            croniter(cron_expr, base_date)
            return True, "Valid cron expression", None
        except Exception as e:
            return False, f"Invalid cron expression: {str(e)}", str(e)

    def get_next_runs(self, cron_expr, count=5, base_date=None):
        """Get next N run times for a cron expression"""
        if base_date is None:
            base_date = datetime.now()
        
        try:
            cron = croniter(cron_expr, base_date)
            runs = []
            for _ in range(count):
                next_run = cron.get_next(datetime)
                runs.append(next_run.isoformat())
            return runs
        except Exception as e:
            return []

    def explain_cron(self, cron_expr):
        """Provide a human-readable explanation of the cron expression"""
        if cron_expr.startswith('@'):
            explanations = {
                '@yearly': 'Once yearly (0 0 1 1 *)',
                '@annually': 'Once yearly (0 0 1 1 *)',
                '@monthly': 'Once monthly (0 0 1 * *)',
                '@weekly': 'Once weekly (0 0 * * 0)',
                '@daily': 'Once daily (0 0 * * *)',
                '@midnight': 'Once daily at midnight (0 0 * * *)',
                '@hourly': 'Once hourly (0 * * * *)'
            }
            return explanations.get(cron_expr.lower(), f"Unknown @ shortcut: {cron_expr}")
        
        parts = cron_expr.split()
        if len(parts) != 5:
            return "Invalid cron expression format"
        
        minute, hour, day, month, weekday = parts
        
        explanation = []
        explanation.append(f"Every ")
        
        # Minutes
        if minute == '*':
            explanation.append("minute")
        elif minute.isdigit():
            explanation.append(f"minute {minute}")
        elif '/' in minute:
            if minute.startswith('*/'):
                interval = minute[2:]
                explanation.append(f"minute interval of {interval}")
            else:
                range_part, interval = minute.split('/')
                explanation.append(f"{range_part} minute interval of {interval}")
        elif '-' in minute:
            explanation.append(f"minutes {minute}")
        elif ',' in minute:
            explanation.append(f"minutes {minute}")
        
        # Hours
        if hour != '*':
            if hour.isdigit():
                explanation.append(f"past hour {hour}")
            elif '-' in hour:
                explanation.append(f"past hours {hour}")
            elif ',' in hour:
                explanation.append(f"past hours {hour}")
            elif '/' in hour:
                if hour.startswith('*/'):
                    interval = hour[2:]
                    explanation.append(f"at every {interval} hour")
                else:
                    range_part, interval = hour.split('/')
                    explanation.append(f"past hours {range_part} at interval {interval}")
        
        # Day of month
        if day != '*':
            if day.isdigit():
                explanation.append(f"on day {day} of the month")
            elif '-' in day:
                explanation.append(f"on days {day} of the month")
            elif ',' in day:
                explanation.append(f"on days {day} of the month")
            elif '/' in day:
                if day.startswith('*/'):
                    interval = day[2:]
                    explanation.append(f"every {interval} day of the month")
        
        # Month
        if month != '*':
            month_names = {
                '1': 'January', '2': 'February', '3': 'March', '4': 'April',
                '5': 'May', '6': 'June', '7': 'July', '8': 'August',
                '9': 'September', '10': 'October', '11': 'November', '12': 'December'
            }
            if month.isdigit():
                month_name = month_names.get(month, month)
                explanation.append(f"in {month_name}")
            elif ',' in month:
                month_list = month.split(',')
                month_names_list = [month_names.get(m, m) for m in month_list]
                explanation.append(f"in months {', '.join(month_names_list)}")
        
        # Day of week
        if weekday != '*':
            weekday_names = {
                '0': 'Sunday', '1': 'Monday', '2': 'Tuesday', '3': 'Wednesday',
                '4': 'Thursday', '5': 'Friday', '6': 'Saturday', '7': 'Sunday'
            }
            if weekday.isdigit():
                weekday_name = weekday_names.get(weekday, weekday)
                explanation.append(f"on {weekday_name}")
            elif ',' in weekday:
                weekday_list = weekday.split(',')
                weekday_names_list = [weekday_names.get(w, w) for w in weekday_list]
                explanation.append(f"on {', '.join(weekday_names_list)}")
        
        return " ".join(explanation)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Cron Expression Validator')
    parser.add_argument('expression', help='Cron expression to validate')
    parser.add_argument('--explain', action='store_true', help='Explain the cron expression')
    parser.add_argument('--next-runs', type=int, default=0, help='Show next N run times')
    parser.add_argument('--base-time', help='Base time for calculations (ISO format)')
    
    args = parser.parse_args()
    
    validator = CronValidator()
    
    if args.base_time:
        base_date = datetime.fromisoformat(args.base_time)
    else:
        base_date = datetime.now()
    
    # Basic validation
    is_valid, msg = validator.validate_basic_syntax(args.expression)
    print(f"Basic syntax: {'VALID' if is_valid else 'INVALID'} - {msg}")
    
    # Complete validation
    is_valid, msg, err = validator.validate_complete(args.expression, base_date)
    print(f"Complete validation: {'VALID' if is_valid else 'INVALID'} - {msg}")
    
    if args.explain:
        explanation = validator.explain_cron(args.expression)
        print(f"Explanation: {explanation}")
    
    if args.next_runs > 0:
        next_runs = validator.get_next_runs(args.expression, args.next_runs, base_date)
        print(f"Next {args.next_runs} run times:")
        for i, run in enumerate(next_runs, 1):
            print(f"  {i}. {run}")


if __name__ == "__main__":
    main()