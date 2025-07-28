#!/usr/bin/env python3
"""
Script to fix CSV encoding issues by converting the file to UTF-8
"""
import os
import csv
import sys

def fix_csv_encoding():
    """Convert CSV file to proper UTF-8 encoding"""
    input_files = [
        'devweb.csv',
        'static/devweb.csv'
    ]
    
    possible_encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1', 'windows-1252']
    
    for input_file in input_files:
        if os.path.exists(input_file):
            print(f"Found CSV file: {input_file}")
            
            # Try to read with different encodings
            for encoding in possible_encodings:
                try:
                    with open(input_file, 'r', encoding=encoding) as f:
                        content = f.read()
                        # Test if we can create a CSV reader
                        f.seek(0)
                        reader = csv.DictReader(f)
                        rows = list(reader)
                        
                    print(f"Successfully read {input_file} with {encoding} encoding")
                    print(f"Found {len(rows)} rows")
                    
                    # Create backup
                    backup_file = input_file + '.backup'
                    if not os.path.exists(backup_file):
                        with open(backup_file, 'w', encoding=encoding) as f:
                            f.write(content)
                        print(f"Created backup: {backup_file}")
                    
                    # Write as UTF-8
                    output_file = input_file.replace('.csv', '_utf8.csv')
                    with open(output_file, 'w', encoding='utf-8', newline='') as f:
                        if rows:
                            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                            writer.writeheader()
                            writer.writerows(rows)
                    
                    print(f"Created UTF-8 version: {output_file}")
                    
                    # Replace original file
                    os.replace(output_file, input_file)
                    print(f"Replaced {input_file} with UTF-8 version")
                    
                    return True
                    
                except (UnicodeDecodeError, UnicodeError, Exception) as e:
                    print(f"Failed to read with {encoding}: {e}")
                    continue
            
            print(f"Could not read {input_file} with any encoding")
    
    print("No CSV files found to fix")
    return False

def create_sample_csv():
    """Create a sample CSV file if none exists"""
    sample_data = [
        {
            'Dimensions': 'Build and Deployment',
            'Sub-Dimensions': 'Build',
            'Questions': 'Do you have a defined and documented build and deployment process?',
            'Description': 'A build process defines how source code is compiled, tested, and packaged.',
            'Options': 'A) No defined process; builds and deployment are manual or ad hoc.',
            'Scores': '1',
            'Comment': '',
            'Score Earned': '',
            'Dimension Score': '',
            'Final Score': ''
        },
        {
            'Dimensions': '',
            'Sub-Dimensions': '',
            'Questions': '',
            'Description': '',
            'Options': 'B) Some projects have defined processes, but these are undocumented and inconsistent.',
            'Scores': '2',
            'Comment': '',
            'Score Earned': '',
            'Dimension Score': '',
            'Final Score': ''
        },
        {
            'Dimensions': '',
            'Sub-Dimensions': '',
            'Questions': '',
            'Description': '',
            'Options': 'C) A documented process exists but lacks adoption in all teams.',
            'Scores': '3',
            'Comment': '',
            'Score Earned': '',
            'Dimension Score': '',
            'Final Score': ''
        },
        {
            'Dimensions': '',
            'Sub-Dimensions': '',
            'Questions': '',
            'Description': '',
            'Options': 'D) All teams follow a consistent, well-documented process.',
            'Scores': '4',
            'Comment': '',
            'Score Earned': '',
            'Dimension Score': '',
            'Final Score': ''
        },
        {
            'Dimensions': '',
            'Sub-Dimensions': '',
            'Questions': '',
            'Description': '',
            'Options': 'E) Processes are optimized, automated, and integrated with CI/CD.',
            'Scores': '5',
            'Comment': '',
            'Score Earned': '',
            'Dimension Score': '',
            'Final Score': ''
        }
    ]
    
    # Create static directory if it doesn't exist
    os.makedirs('static', exist_ok=True)
    
    output_file = 'static/devweb.csv'
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=sample_data[0].keys())
        writer.writeheader()
        writer.writerows(sample_data)
    
    print(f"Created sample CSV file: {output_file}")
    return True

if __name__ == '__main__':
    print("CSV Encoding Fix Tool")
    print("=" * 50)
    
    if not fix_csv_encoding():
        print("Creating sample CSV file...")
        create_sample_csv()
    
    print("Done!")