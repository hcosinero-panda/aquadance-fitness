import os

# Delete the conflicting migration file
migration_path = r"c:\Users\harve\OneDrive\Documents\AQUADANCE FITNESS\core\migrations\0002_member_unique_code.py"

if os.path.exists(migration_path):
    os.remove(migration_path)
    print("✓ Deleted 0002_member_unique_code.py")
else:
    print("File not found")
