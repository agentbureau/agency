"""Instance/project configuration hierarchy resolution."""

def resolve(project_value, instance_value):
    """Return project_value if not None, else instance_value. Strict None check."""
    return project_value if project_value is not None else instance_value
