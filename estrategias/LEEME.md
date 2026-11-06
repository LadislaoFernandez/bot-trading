# Catálogo de estrategias

Cada archivo `.json` de esta carpeta es una estrategia definida como datos (sin código). La app las carga al iniciar
y aparecen en la sección Estrategias junto a las incorporadas. El formato está explicado en `reglas.py`.

Para agregar una estrategia al catálogo de todos los usuarios:

1. Alguien la propone desde la app (laboratorio → "Proponer para todos"), lo que abre un *issue* en GitHub con el JSON.
2. Se copia el JSON acá, las pruebas de GitHub Actions la validan, y se publica una versión nueva.
3. Las apps instaladas la reciben con la actualización.
