import importlib.util
import inspect
import os

from api.evaluator import EvaluatorBase


# Loading plugin module
def load_module_from_file(filepath):
    spec = importlib.util.spec_from_file_location("plugin_module", filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Check if a class implementes EvaluatorBase and its methods
def check_implementation(module):
    for name, obj in inspect.getmembers(module, inspect.isclass):
        # Comprobar si es una subclase de EvaluatorBase
        if issubclass(obj, EvaluatorBase) and obj is not EvaluatorBase:
            # Obtener los métodos abstractos que están definidos en EvaluatorBase
            abstract_methods = {
                name
                for name, method in inspect.getmembers(
                    EvaluatorBase, inspect.isfunction
                )
            }
            # Obtener los métodos redefinidos en la clase
            redefined_methods = {
                name for name, method in inspect.getmembers(obj, inspect.isfunction)
            }

            # Comparar los métodos de EvaluatorBase con los de la subclase para ver cuáles fueron reimplementados
            reimplemented_methods = []
            for method_name in redefined_methods:
                base_method = getattr(EvaluatorBase, method_name, None)
                subclass_method = getattr(obj, method_name, None)

                # Comparar las referencias de los métodos para ver si son diferentes (si fueron reimplementados)
                if base_method and subclass_method and base_method != subclass_method:
                    reimplemented_methods.append(method_name)

            # Mostrar los métodos reimplementados
            print(
                f"'{obj.__name__}' ha reimplementado los siguientes métodos: {sorted(reimplemented_methods)}"
            )

            # Comprobar si todos los métodos abstractos han sido redefinidos
            missing_methods = abstract_methods - redefined_methods
            if not missing_methods:
                print(
                    f"'{obj.__name__}' ha redefinido todos los métodos de EvaluatorBase."
                )
            else:
                print(
                    f"'{obj.__name__}' NO ha redefinido los siguientes métodos: {missing_methods}"
                )


# Looking for plugins
def check_plugins_in_directory(directory):
    for root, dirs, files in os.walk(directory):
        if "plugin.py" in files:
            plugin_path = os.path.join(root, "plugin.py")
            dir_name = os.path.basename(root)  # Obtener el nombre del directorio actual
            print(f"Comprobando plugin en el directorio: {dir_name}")
            try:
                module = load_module_from_file(plugin_path)
                check_implementation(module)
            except Exception as e:
                print(f"Error al cargar {plugin_path}: {e}")


# Ejemplo de uso
plugin_directory = "./plugins"
check_plugins_in_directory(plugin_directory)
