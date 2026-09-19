# Recálculo RTK a Coordenadas Ajustadas — complemento de QGIS

Recalcula un archivo de puntos levantados con **RTK** (base de coordenadas
**libres**, tomadas en campo) hacia las coordenadas **ajustadas** que
resultan del **postproceso estático** de esa misma base. Recalcula tanto
las coordenadas **planas** (proyectadas) como las **geográficas**
(longitud/latitud).

## Fundamento

Cuando se levanta una red con RTK usando una sola base, cada punto rover
queda definido por un **vector de línea base** (ΔX, ΔY, ΔZ) respecto a la
base, obtenido de la solución de fase portadora. Ese vector es una
magnitud física y no depende de qué coordenada se le haya asignado a la
base en el momento del levantamiento. Por lo tanto, si:

- la base tenía una coordenada **libre** (autónoma/arbitraria) durante el
  levantamiento, y
- luego, por **postproceso estático**, se obtiene su coordenada
  **ajustada** (ligada a la red de referencia, p. ej. MAGNA-SIRGAS),

entonces la coordenada correcta de cualquier punto radiado es:

```
punto_ajustado = punto_libre + (base_ajustada − base_libre)
```

Es decir, una **traslación rígida**: el mismo desplazamiento (dx, dy, dz)
se suma a todos los puntos del levantamiento. Esta corrección es exacta
para el caso de una sola base y válida en la práctica para radiaciones
RTK de corta y mediana distancia (no incluye rotación ni escala; para
levantamientos que combinan varias bases con orientaciones distintas se
recomienda un ajuste de red completo, no una simple traslación).

## Qué hace el complemento

1. Solicita la coordenada de la **base libre** (X/Este, Y/Norte, Z) y de
   la **base ajustada** (X/Este, Y/Norte, Z).
2. Calcula el vector de traslación (ΔX, ΔY, ΔZ).
3. Carga un archivo **CSV delimitado por comas** con los puntos
   levantados, y permite elegir cuáles columnas corresponden a X, Y, Z
   (y opcionalmente un ID).
4. Aplica la traslación a todas las filas del CSV.
5. Reproyecta los puntos ajustados desde el CRS plano indicado hacia un
   CRS geográfico (por defecto MAGNA-SIRGAS geográfico, EPSG:4686;
   puede cambiarse a WGS84 u otro desde el selector de CRS).
6. Genera un nuevo CSV con las columnas originales más:
   `X_ajustada`, `Y_ajustada`, `Z_ajustada`, `Lon_ajustada`, `Lat_ajustada`.
7. Opcionalmente agrega al proyecto de QGIS una capa de puntos con las
   coordenadas ajustadas (y, si se desea, otra con las originales/libres,
   útil para comparar visualmente el desplazamiento).
8. Opcionalmente exporta los puntos ajustados también como **Shapefile
   (.shp)** y/o **DXF (.dxf)**, para llevarlos a otro software (AutoCAD,
   Civil3D, otro SIG, etc.).

## Instalación

**Opción A — Instalar desde ZIP (recomendada):**

1. Comprima la carpeta `recalculo_rtk` en un archivo `.zip`
   (ya viene comprimida como `recalculo_rtk.zip`).
2. En QGIS: `Complementos → Administrar e instalar complementos… →
   Instalar desde ZIP`.
3. Seleccione el archivo `recalculo_rtk.zip` y haga clic en
   `Instalar complemento`.
4. Active la casilla del complemento "Recalculo RTK a Coordenadas
   Ajustadas" en la lista de complementos instalados, si no queda
   activado automáticamente.

**Opción B — Copiar manualmente la carpeta:**

Copie la carpeta `recalculo_rtk` dentro de la carpeta de complementos de
su perfil de QGIS:

- **Windows:**
  `C:\Users\<usuario>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
- **Linux:**
  `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **macOS:**
  `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

Luego reinicie QGIS y actívelo en
`Complementos → Administrar e instalar complementos → Instalados`.

Una vez instalado aparece un ícono en la barra de herramientas y una
entrada en el menú **Complementos → Recálculo RTK a Ajustada**.

## Tamaño de la ventana

La ventana del complemento se puede agrandar, achicar o maximizar libremente
arrastrando sus bordes (o con el botón de maximizar), igual que cualquier otra
ventana de Windows/Linux/macOS. Si la achica y el contenido no cabe completo,
aparece una barra de desplazamiento vertical para recorrerlo; el registro de
estado y los botones "Calcular y exportar" / "Cerrar" quedan siempre visibles
en la parte inferior, sin importar cuánto se desplace el contenido de arriba.

## Uso

1. Abra el complemento (ícono de la barra de herramientas o menú de
   Complementos).
2. Ingrese la coordenada de la **base libre** (la que usó el equipo RTK
   en campo, antes del ajuste) en X/Este, Y/Norte y Z.
3. Ingrese la coordenada de la **base ajustada** obtenida del postproceso
   estático (la definitiva, ligada a la red de referencia).
4. Seleccione el archivo **CSV** con los puntos a recalcular (debe estar
   delimitado por comas). El complemento leerá el encabezado y le
   permitirá escoger:
   - Columna X / Este (obligatoria)
   - Columna Y / Norte (obligatoria)
   - Columna Z / Elevación (opcional)
   - Columna ID (opcional, solo para identificar el punto)
5. Verifique/ajuste el **CRS plano** en el que están las coordenadas X, Y
   del CSV (por defecto toma el CRS del proyecto/lienzo actual) y el
   **CRS geográfico** de salida (por defecto MAGNA-SIRGAS geográfico,
   EPSG:4686).
6. Indique dónde guardar el **CSV de salida** (por defecto se sugiere
   `<nombre_original>_ajustado.csv`).
7. Marque si desea agregar la(s) capa(s) de puntos al proyecto.
8. Si además necesita el resultado en **Shapefile** y/o **DXF**, marque la
   casilla correspondiente e indique (o acepte la ruta sugerida) dónde
   guardar cada archivo. Estos dos formatos exportan siempre los **puntos
   ajustados** (el resultado principal del recálculo).
9. Haga clic en **"Calcular y exportar"**.

El cuadro de registro (parte inferior del diálogo) muestra el vector de
traslación aplicado, cuántos puntos se procesaron correctamente y el
detalle de cualquier fila que no pudo interpretarse (por ejemplo, celdas
vacías o con texto donde se esperaba un número).

## Formato esperado del CSV de entrada

- Delimitado por **comas** (`,`).
- Primera fila = encabezados de columna.
- Los valores numéricos pueden usar punto o coma como separador decimal
  (el complemento intenta interpretar ambos).
- No es necesario que las columnas estén en un orden particular: se
  eligen por nombre en el propio diálogo.

Ejemplo (`puntos_ejemplo.csv`):

```
ID,Este,Norte,Elevacion,Descripcion
P1,1000000.000,1000000.000,2600.000,Mojón
P2,1000015.320,999998.750,2599.850,PR-1
P3,999987.100,1000022.400,2601.120,PR-2
```

## Exportación a Shapefile y a DXF

- **Shapefile (.shp):** se exporta la capa de puntos ajustados completa,
  con todas las columnas originales del CSV más las columnas calculadas
  (`X_ajustada`, `Y_ajustada`, `Z_ajustada`, `Lon_ajustada`,
  `Lat_ajustada`). Si se seleccionó una columna de elevación, la
  geometría queda en 3D (`PointZ`), es decir, el shapefile trae la
  elevación tanto en la geometría como en el atributo `Z_ajustada`.
  Limitación propia del formato ESRI Shapefile: los nombres de columna
  se truncan a 10 caracteres.
- **DXF (.dxf):** el formato DXF no tiene una tabla de atributos como
  tal, así que se exporta únicamente la geometría de los puntos
  ajustados (en 3D si hay elevación) junto con una etiqueta de texto por
  punto — la columna ID si la seleccionó, o un consecutivo `P1, P2, ...`
  si no. Esa etiqueta aparece en AutoCAD/Civil3D como una entidad de
  texto junto a cada punto (convención del driver DXF de GDAL/OGR: un
  campo llamado exactamente `Text`).
- Ambos formatos son opcionales e independientes entre sí y del CSV de
  salida, que siempre se genera.

## Notas técnicas

- La reproyección se realiza con el motor de transformación de
  coordenadas de QGIS (PROJ), por lo que soporta cualquier CRS conocido
  por QGIS, incluyendo las distintas zonas MAGNA-SIRGAS (Origen Nacional,
  Este, Oeste, Este Central, etc.). Seleccione la zona correcta según el
  levantamiento: el complemento no la adivina.
- El método aplicado es una **traslación pura** (misma ΔX, ΔY, ΔZ para
  todos los puntos). No corrige rotación ni escala; es la práctica
  estándar cuando se trabaja con una sola base RTK.
- Los campos de las capas de puntos generadas se crean como texto para
  evitar problemas de tipos con datos heterogéneos del CSV; la geometría
  sí queda en las coordenadas numéricas correctas (en 3D si hay
  elevación). Si necesita campos numéricos, puede exportar la capa
  (`Guardar como…`) y ajustar los tipos de campo en ese paso.
- La exportación a Shapefile/DXF usa `QgsVectorFileWriter` con
  compatibilidad para las distintas firmas que esa clase ha tenido a
  través de las versiones de QGIS, de modo que funciona tanto en
  QGIS 3.16+ como en QGIS 4.x.
- El archivo `core.py` contiene toda la aritmética del complemento sin
  ninguna dependencia de QGIS, y se puede probar de forma aislada con
  Python estándar (ver `test_core.py`).

## Autor

Edwin Arley Castellanos Martínez — topógrafo y agrimensor catastral.
