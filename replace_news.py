#!/usr/bin/env python3
"""Replace news arrays in index.html with newly extracted data."""

import re

INDEX_FILE = "/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/index.html"
GENERATED_FILE = "/Users/bainian/WorkBuddy/2026-06-25-10-20-28/zhenbao-daily-news/generated_news_arrays.js"

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def replace_array(content, array_name, new_array_text):
    """Replace a const array definition in the content."""
    # Pattern: const arrayName = [ ... ];
    # Need to handle multi-line arrays
    pattern = rf'(const {re.escape(array_name)} = \[)\n.*?(\n\];)'
    replacement = rf'\g<1>\n{new_array_text}\g<2>'
    
    # Actually, let's use a simpler approach - find the start and end
    start_marker = f'const {array_name} = ['
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print(f"  WARNING: Could not find '{array_name}'")
        return content
    
    # Find the closing ];
    # Search from start_idx for "];" at the start of a line
    search_start = start_idx + len(start_marker)
    end_idx = content.find('\n];', search_start)
    if end_idx == -1:
        print(f"  WARNING: Could not find end of '{array_name}'")
        return content
    
    end_idx += 3  # Include the "];"
    
    old_text = content[start_idx:end_idx]
    
    # Extract the new array content (everything between [ and ];)
    new_start = new_array_text.find('[')
    new_end = new_array_text.rfind('];')
    if new_start == -1 or new_end == -1:
        print(f"  WARNING: Could not parse new array text for '{array_name}'")
        return content
    
    new_content_text = new_array_text[new_start+1:new_end].strip()
    new_full = f'const {array_name} = [\n{new_content_text}\n];'
    
    content = content[:start_idx] + new_full + content[end_idx:]
    print(f"  Replaced '{array_name}' successfully")
    return content

def extract_array_from_generated(generated_content, array_name):
    """Extract a specific array from the generated JS file."""
    start_marker = f'const {array_name} = ['
    start_idx = generated_content.find(start_marker)
    if start_idx == -1:
        return None
    
    # Find the closing ];
    search_start = start_idx + len(start_marker)
    end_idx = generated_content.find('\n];', search_start)
    if end_idx == -1:
        return None
    
    end_idx += 3
    return generated_content[start_idx:end_idx]

def main():
    print("Reading files...")
    index_content = read_file(INDEX_FILE)
    generated_content = read_file(GENERATED_FILE)
    
    print(f"Index file: {len(index_content)} chars")
    print(f"Generated file: {len(generated_content)} chars")
    
    # Arrays to replace (in order of appearance in index.html)
    arrays_to_replace = [
        'mockHotNewsDomestic',
        'mockHotNewsDomesticExtra',
        'mockHotNewsInternational',
        'mockHotNewsInternationalExtra',
        'mockEntertainment',
        'mockEntertainmentExtra',
        'mockHenanNews',
        'mockCslOtherTeams',
    ]
    
    print("\nReplacing arrays...")
    for array_name in arrays_to_replace:
        new_array = extract_array_from_generated(generated_content, array_name)
        if new_array:
            index_content = replace_array(index_content, array_name, new_array)
        else:
            print(f"  WARNING: '{array_name}' not found in generated file!")
    
    print(f"\nWriting updated index.html ({len(index_content)} chars)...")
    write_file(INDEX_FILE, index_content)
    print("Done!")

if __name__ == '__main__':
    main()
