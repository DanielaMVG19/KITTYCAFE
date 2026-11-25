# Cafetería Hello Kitty

Proyecto web local en Python 3. Incluye SQLite para guardar el menú y los pedidos, seis fotos de ejemplo y una interfaz en HTML, CSS y JavaScript.

## Abrir en Windows

1. Descomprime el ZIP. Abre PowerShell dentro de la carpeta en la que se ve el archivo `app.py`.
2. Ejecuta `python app.py`. También puedes usar `py app.py`.
3. Abre [http://127.0.0.1:8000](http://127.0.0.1:8000) en tu navegador. Mantén PowerShell abierto.

Si todavía tienes abierta la aplicación anterior en el puerto 8000, detenla con Ctrl+C en su terminal antes de iniciar esta. En macOS o Linux puedes ejecutar `python3 app.py`.

## Probar los paneles

- **Cliente.** Agrega bebidas o postres al carrito, ajusta cantidades y confirma el pedido. El pago es simulado y se descarga un ticket TXT con folio, precios, cantidades y total en pesos mexicanos.
- **Administración.** Entra con la contraseña de prueba `Kitty2026`. Puedes consultar, agregar, editar y eliminar productos. Acepta fotos JPG, PNG o WebP de hasta 2 MB.

La aplicación crea `cafeteria_kitty.sqlite3` automáticamente en el primer arranque. Puedes cambiar la contraseña con la variable de entorno `KITTY_ADMIN_PASSWORD`. Solo necesitas Python 3. El proyecto no representa a Sanrio ni a una cafetería oficial.
