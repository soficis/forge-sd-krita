import ast
import os

def check_syntax(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        return True, None
    except SyntaxError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def main():
    root_dir = 'forge'
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                success, error = check_syntax(path)
                if not success:
                    print(f"ERROR in {path}: {error}")
                else:
                    print(f"OK: {path}")

if __name__ == "__main__":
    main()
