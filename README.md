# Dashboard NPS GALAXIA

Dashboard local, editable y actualizable para demostrar Nivel 1 del punto 2.2.5.6.2 "NPS: Net Promoter Score".

## Cómo usarlo

1. Dejar los Excel en `N:\Tomas\DASHBOARDS\nps`.
2. Ejecutar desde esta carpeta:

```powershell
node server.mjs
```

3. Abrir la URL que muestre la consola. Por defecto es `http://127.0.0.1:5173`; si ese puerto está ocupado, el servidor prueba el siguiente disponible.
4. Para recargar datos luego de reemplazar Excel, usar el botón `Actualizar Excel`.
5. Para exportar el plan mensual de detractores y pasivos, usar `Exportar plan`.

## Archivos creados

- `scripts/extract-nps-data.ps1`: lee automáticamente los `.xlsx` de `N:\Tomas\DASHBOARDS\nps` sin modificar los originales.
- `public/data/raw-data.json`: datos extraídos para el dashboard.
- `public/index.html`: estructura del dashboard.
- `public/app.js`: modelo de datos, medidas, filtros, rankings, planes y auditoría.
- `public/styles.css`: diseño corporativo GALAXIA.
- `server.mjs`: servidor local y actualización automática de datos.

## Detección real de archivos

Archivo NPS detectado: `nps 2026.xlsx`, hoja `Export`.

Columnas encontradas:

- `FECHA_ENC`
- `COD_CLIENTE_DISTRIBUIDOR_ACTIVO`
- `NOMBRE_CLIENTE`
- `DESC_LOCALIDAD`
- `SCORE`
- `COD_DESC_SEGMENTO_MKT`
- `COD_DESC_SEGMENTO_VENTA`
- `COD_DISTRIBUIDOR`
- `DDC_NAME`
- `CATEGORIA`
- `PRIMER_DRIVER`
- `SECONDARY_DRIVER`
- `COMENTARIO`

Archivo de clientes detectado: `20260511104225plantillaClientesAR.xlsx`.

Hojas relevantes:

- `Clientes`
- `Rutas de Venta`

Relación aplicada:

`NPS[COD_CLIENTE_DISTRIBUIDOR_ACTIVO]` -> quitar prefijo `COD_DISTRIBUIDOR` -> `Clientes[Cliente]` -> `Clientes[Código Ruta Vta.]` -> `Rutas de Venta[Código]` -> `Rutas de Venta[Vendedor]`.

La columna `AU` no existe en el Excel NPS inspeccionado. El dashboard lo documenta en Auditoría y usa la relación por cliente/ruta como mejor interpretación disponible, con fallback a `DDC_NAME`.

## Columnas calculadas y medidas

Columnas calculadas:

- `Tipo_NPS`: Detractor 0-6, Pasivo 7-8, Promotor 9-10.
- `Es_Detractor`, `Es_Pasivo`, `Es_Promotor`.
- `Mes`, `Año`, `Año-Mes`, `Nombre del mes`, `Trimestre`.
- `Driver`, `Subdriver`, `Promotor`, `Ruta`.
- `Punto_de_Dolor`: se considera verdadero cuando `SECONDARY_DRIVER` o el comentario tiene lenguaje negativo, por ejemplo `no`, `dificil`, `problema`, `falla`, `demora`, `incorrecto`, `pendiente`, `reclamo`, `faltante`, etc. Se excluyen valores neutros como `Ninguno` o `Sin comentario`.

Medidas incluidas:

- Total encuestas.
- Total promotores, pasivos y detractores.
- % promotores, % pasivos y % detractores.
- NPS mensual y acumulado anual.
- Variación NPS vs mes anterior.
- Variación de detractores vs mes anterior.
- Drivers y subdrivers principales de detracción.
- Participación porcentual por driver/subdriver.
- Ranking de promotores por NPS y detractores.
- Clientes detractores, pasivos y recurrentes para plan de acción.

Nota de cálculo NPS: las medidas de NPS, porcentajes y total encuestas cuentan respuestas únicas. El archivo NPS puede traer varias filas para la misma encuesta cuando la respuesta se abre por driver/subdriver; para el cálculo del manual se deduplica por `FECHA_ENC + COD_CLIENTE_DISTRIBUIDOR_ACTIVO + SCORE`.

## Páginas

1. Resumen ejecutivo NPS.
2. Driver y Subdriver.
3. Puntos de dolor.
4. Planes de acción sugeridos.
5. Plan mensual para detractores y pasivos.
6. Promotores / Rutas.
7. Auditoría GALAXIA 100%.

Agregado de seguimiento:

- En `Plan mensual` se incluye una planilla editable para comentarios de acciones realizadas con clientes Promotores, Pasivos y Detractores.
- La exportación a Excel incluye columnas para `Accion realizada`, `Comentario plan`, `Fecha accion`, `Responsable`, `Prioridad` y `Estado`.
- La misma página muestra clientes que se repiten mes a mes en el acumulado anual, para seguimiento de recurrencia.
- Los comentarios escritos en la planilla se guardan automáticamente en el navegador con `localStorage`; al refrescar la página se mantienen en la misma PC/navegador. El botón `Borrar comentarios` limpia ese guardado local.
- El botón `App planes` funciona como acceso directo a la app de planes de acción. La primera vez pide la URL y la guarda en el navegador. Para cambiarla, hacer clic derecho sobre el botón.
