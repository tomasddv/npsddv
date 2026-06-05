# Publicar NPS en Streamlit Cloud

## Archivos a subir a GitHub

- `streamlit_app.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `PUBLICAR_STREAMLIT_NPS.md`
- carpeta `.streamlit`, pero solo:
  - `config.toml`
  - `secrets.example.toml`

No subir:

- `.streamlit/secrets.toml`
- `.cloud_data/`
- `node_modules/`
- `__pycache__/`

## Streamlit Cloud

Crear una app nueva desde GitHub con:

```text
Main file path: streamlit_app.py
Branch: main
```

En `Secrets` pegar:

```toml
GOOGLE_DRIVE_NPS_URL = "https://drive.google.com/drive/folders/1JcQyaMxXY4ZcRooXPgWGZ5QjWXUHzsil?usp=drive_link"
PLANES_ACCION_NPS_API_URL = "https://script.google.com/macros/s/AKfycbzAW3Cq82gjIEVZq25mExuEUpc2ZgEFlq9DSsLOonqaQUK7DV7_cAnCcVwAJqCw3pVPPw/exec"
FORCE_GDRIVE_REFRESH = "false"
GDRIVE_CACHE_TTL_HOURS = "6"
```

## Actualizar datos

Reemplazar en Drive:

- `NPS 2026.xlsx`
- `20260511104225plantillaClientesAR.xlsx`

Luego en Streamlit Cloud usar `Manage app` > `Reboot app`.

Si no actualiza, cambiar temporalmente:

```toml
FORCE_GDRIVE_REFRESH = "true"
```

reiniciar, y despues volver a `"false"`.

## Permisos del Apps Script

Si los planes no cargan o no guardan, revisar el despliegue del Apps Script:

- Tipo: Aplicacion web
- Ejecutar como: Yo
- Quien tiene acceso: Cualquier persona

Despues de cambiar permisos, copiar la URL nueva que termina en `/exec` y actualizar el secret `PLANES_ACCION_NPS_API_URL`.
