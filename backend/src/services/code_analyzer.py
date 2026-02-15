"""Code structure analyzer for building call graphs and understanding execution flow.

This module uses Python AST to analyze the codebase structure and build
a template call graph that can be used with trace logs.
"""

import ast
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


class CallGraphNode:
    """Represents a node in the call graph."""
    
    def __init__(self, name: str, node_type: str, module: str):
        self.name = name
        self.type = node_type  # 'function', 'method', 'class'
        self.module = module
        self.calls: list[str] = []  # Names of functions/methods called
        self.called_by: list[str] = []  # Names of functions/methods that call this
    
    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'type': self.type,
            'module': self.module,
            'calls': self.calls,
            'called_by': self.called_by,
        }


class CodeAnalyzer:
    """Analyzes Python code structure to build call graphs."""
    
    def __init__(self, src_dir: str = "backend/src"):
        """Initialize code analyzer.
        
        Args:
            src_dir: Source code directory to analyze
        """
        self.src_dir = Path(src_dir)
        self.call_graph: dict[str, CallGraphNode] = {}
        self.modules: dict[str, dict[str, Any]] = {}
    
    def analyze(self) -> dict[str, Any]:
        """Analyze the source code and build call graph.
        
        Returns:
            Dictionary containing modules and call graph information
        """
        # Walk through source directory
        python_files = list(self.src_dir.rglob("*.py"))
        
        logger.info(f"Found {len(python_files)} Python files to analyze")
        
        for file_path in python_files:
            self._analyze_file(file_path)
        
        # Build simplified call graph
        call_graph_dict = {
            name: node.to_dict()
            for name, node in self.call_graph.items()
        }
        
        return {
            'modules': self.modules,
            'call_graph': call_graph_dict,
            'stats': {
                'total_modules': len(self.modules),
                'total_nodes': len(self.call_graph),
            }
        }
    
    def _analyze_file(self, file_path: Path) -> None:
        """Analyze a single Python file.
        
        Args:
            file_path: Path to Python file
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse AST
            tree = ast.parse(content, filename=str(file_path))
            
            # Get module name from file path
            module_name = self._get_module_name(file_path)
            
            # Initialize module info
            module_info: dict[str, Any] = {
                'classes': {},
                'functions': [],
                'imports': [],
            }
            
            # Analyze top-level definitions
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = self._analyze_class(node, module_name)
                    module_info['classes'][node.name] = class_info
                
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    # Top-level function
                    if self._is_top_level(node):
                        module_info['functions'].append(node.name)
                        self._add_to_call_graph(
                            name=f"{module_name}.{node.name}",
                            node_type='function',
                            module=module_name,
                            ast_node=node,
                        )
                
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    module_info['imports'].extend(self._extract_imports(node))
            
            self.modules[module_name] = module_info
        
        except Exception as e:
            logger.warning(f"Failed to analyze {file_path}: {e}")
    
    def _analyze_class(self, node: ast.ClassDef, module_name: str) -> dict[str, Any]:
        """Analyze a class definition.
        
        Args:
            node: AST ClassDef node
            module_name: Module containing the class
            
        Returns:
            Dictionary with class information
        """
        class_info: dict[str, Any] = {
            'methods': [],
            'bases': [self._get_name(base) for base in node.bases],
        }
        
        # Analyze methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                class_info['methods'].append(item.name)
                
                # Add method to call graph
                full_name = f"{module_name}.{node.name}.{item.name}"
                self._add_to_call_graph(
                    name=full_name,
                    node_type='method',
                    module=module_name,
                    ast_node=item,
                )
        
        return class_info
    
    def _add_to_call_graph(
        self,
        name: str,
        node_type: str,
        module: str,
        ast_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """Add a function/method to the call graph.
        
        Args:
            name: Full qualified name
            node_type: Type of node ('function' or 'method')
            module: Module name
            ast_node: AST node
        """
        if name not in self.call_graph:
            self.call_graph[name] = CallGraphNode(name, node_type, module)
        
        graph_node = self.call_graph[name]
        
        # Extract function calls from body
        for child in ast.walk(ast_node):
            if isinstance(child, ast.Call):
                called_name = self._extract_call_name(child)
                if called_name and called_name not in graph_node.calls:
                    graph_node.calls.append(called_name)
    
    def _extract_call_name(self, node: ast.Call) -> str | None:
        """Extract the name of a function being called.
        
        Args:
            node: AST Call node
            
        Returns:
            Function/method name or None
        """
        func = node.func
        
        if isinstance(func, ast.Name):
            return func.id
        elif isinstance(func, ast.Attribute):
            # Handle method calls like obj.method()
            if isinstance(func.value, ast.Name):
                return f"{func.value.id}.{func.attr}"
            else:
                return func.attr
        
        return None
    
    def _get_module_name(self, file_path: Path) -> str:
        """Convert file path to module name.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            Module name (e.g., 'api.v1.chat')
        """
        # Get relative path from src directory
        try:
            rel_path = file_path.relative_to(self.src_dir)
        except ValueError:
            rel_path = file_path
        
        # Convert to module name
        parts = list(rel_path.parts[:-1]) + [rel_path.stem]
        if parts[-1] == '__init__':
            parts = parts[:-1]
        
        return '.'.join(parts)
    
    def _get_name(self, node: ast.AST) -> str:
        """Get name from AST node.
        
        Args:
            node: AST node
            
        Returns:
            Name string
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        else:
            return str(node.__class__.__name__)
    
    def _is_top_level(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Check if function is at top level (not a method).
        
        Args:
            node: Function AST node
            
        Returns:
            True if top-level function
        """
        # This is a simplified check
        # In practice, we'd need to track the parent context
        return True
    
    def _extract_imports(self, node: ast.Import | ast.ImportFrom) -> list[str]:
        """Extract import names from import statement.
        
        Args:
            node: Import AST node
            
        Returns:
            List of imported names
        """
        imports = []
        
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for alias in node.names:
                    imports.append(f"{node.module}.{alias.name}")
        
        return imports
    
    def get_call_chain(self, start_node: str, max_depth: int = 5) -> list[list[str]]:
        """Get all possible call chains starting from a node.
        
        Args:
            start_node: Starting node name
            max_depth: Maximum depth to traverse
            
        Returns:
            List of call chains (each chain is a list of node names)
        """
        if start_node not in self.call_graph:
            return []
        
        chains: list[list[str]] = []
        
        def dfs(node_name: str, chain: list[str], depth: int) -> None:
            if depth >= max_depth:
                return
            
            if node_name not in self.call_graph:
                return
            
            node = self.call_graph[node_name]
            
            if not node.calls:
                # Leaf node, save chain
                chains.append(chain.copy())
                return
            
            # Continue traversing
            for called in node.calls:
                if called not in chain:  # Avoid cycles
                    dfs(called, chain + [called], depth + 1)
        
        dfs(start_node, [start_node], 0)
        
        return chains


def get_code_analyzer(src_dir: str = "backend/src") -> CodeAnalyzer:
    """Get a CodeAnalyzer instance.
    
    Args:
        src_dir: Source directory to analyze
        
    Returns:
        CodeAnalyzer instance
    """
    return CodeAnalyzer(src_dir)
