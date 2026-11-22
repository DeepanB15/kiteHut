"""Unicode source: multibyte comments, strings and a Unicode identifier."""

GREETING = "こんにちは世界"

café_count = 2


def saluda(nombre):
    """Return a greeting; the docstring and literals are multibyte."""
    return f"¡Hola, {nombre}! — {GREETING}"


def résumé():
    """A function with a non-ASCII identifier is a valid Python symbol."""
    return saluda("mundo") + str(café_count)
