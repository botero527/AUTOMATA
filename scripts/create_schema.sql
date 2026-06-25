-- =============================================================================
-- AUTOMATA — Schema completo en AGP_Ingenieria
-- Notación: [AUTOMATA].[NOMBRE_TABLA]  (schema=AUTOMATA, db=AGP_Ingenieria)
-- Ejecutar como: DevIngenieria @ agpcolombia.database.windows.net
-- =============================================================================

-- Crear schema si no existe
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'AUTOMATA')
    EXEC('CREATE SCHEMA AUTOMATA');
GO

-- =============================================================================
-- PLANOS — Registro maestro de cada archivo DWG procesado
-- =============================================================================
CREATE TABLE [AUTOMATA].[PLANOS] (
    ID                  INT IDENTITY(1,1) PRIMARY KEY,

    -- Identificación del archivo
    VEHICULO            NVARCHAR(150)   NOT NULL,   -- carpeta raíz: 'SUZUKI', 'TOYOTA GR86'
    MARCA               NVARCHAR(100)   NULL,        -- extraído de carpeta_parts[0] si aplica
    MODELO              NVARCHAR(100)   NULL,        -- carpeta_parts[1]
    VERSION             NVARCHAR(100)   NULL,        -- carpeta_parts[2]
    ARCHIVO             NVARCHAR(255)   NOT NULL,    -- '1761 006 005 A.dwg'
    CARPETA             NVARCHAR(500)   NULL,        -- 'V-02/ASTON MARTIN/DBX707'
    CARPETA_PARTS_JSON  NVARCHAR(1000)  NULL,        -- '["V-02","ASTON MARTIN","DBX707"]'
    RUTA_RED_COMPLETA   NVARCHAR(1000)  NULL,        -- UNC completa para re-procesar

    -- Identificación de pieza
    PIEZA_COD           NVARCHAR(5)     NULL,        -- '009', '001', '00' normalizado a 3 dígitos
    PIEZA_NOMBRE        NVARCHAR(100)   NULL,        -- 'Posterior', 'Parabrisas'

    -- Geometría del plano (bounding box DXF)
    DXF_XMIN            FLOAT           NULL,
    DXF_YMIN            FLOAT           NULL,
    DXF_XMAX            FLOAT           NULL,
    DXF_YMAX            FLOAT           NULL,
    DXF_ANCHO           FLOAT           NULL,        -- XMAX - XMIN
    DXF_ALTO            FLOAT           NULL,        -- YMAX - YMIN
    ASPECT_RATIO        FLOAT           NULL,        -- ANCHO / ALTO

    -- Imagen renderizada
    RENDER_PATH         NVARCHAR(500)   NULL,        -- ruta local al PNG
    RENDER_W_PX         INT             NULL,
    RENDER_H_PX         INT             NULL,

    -- Metadata DXF
    DXF_VERSION         NVARCHAR(20)    NULL,        -- 'AC1032' = AutoCAD 2018
    TOTAL_TEXTOS        INT             NULL,        -- cuántos TEXT/MTEXT/ATTRIB extraídos
    TOTAL_CAJETINES     INT             NULL,
    TOTAL_RADIOS        INT             NULL,
    TOTAL_COTAS         INT             NULL,
    TOTAL_LAYERS        INT             NULL,        -- cuántos layers distintos tiene

    -- Control de procesamiento
    FECHA_PROCESO       DATETIME        DEFAULT GETDATE(),
    FECHA_MODIFICACION  DATETIME        NULL,        -- fecha del archivo DWG en red
    HASH_ARCHIVO        NVARCHAR(64)    NULL,        -- SHA256 para detectar cambios
    ESTADO              NVARCHAR(20)    DEFAULT 'OK',-- 'OK','ERROR','PENDIENTE'
    ERROR_MSG           NVARCHAR(1000)  NULL,

    -- Índice único por archivo
    CONSTRAINT UQ_PLANOS_ARCHIVO UNIQUE (VEHICULO, CARPETA, ARCHIVO)
);
GO

CREATE INDEX IX_PLANOS_VEHICULO   ON [AUTOMATA].[PLANOS] (VEHICULO);
CREATE INDEX IX_PLANOS_PIEZA_COD  ON [AUTOMATA].[PLANOS] (PIEZA_COD);
CREATE INDEX IX_PLANOS_ESTADO     ON [AUTOMATA].[PLANOS] (ESTADO);
GO

-- =============================================================================
-- CAJETINES — Cajetín técnico individual dentro de un plano
-- =============================================================================
CREATE TABLE [AUTOMATA].[CAJETINES] (
    ID                  INT IDENTITY(1,1) PRIMARY KEY,
    PLANO_ID            INT             NOT NULL REFERENCES [AUTOMATA].[PLANOS](ID) ON DELETE CASCADE,
    CAJ_INDEX           INT             NOT NULL,    -- índice 0-based dentro del plano

    -- ── Campos técnicos conocidos (columnas propias para queries rápidos) ──
    OFFSET_VAL          FLOAT           NULL,        -- valor numérico: 28, 30, 40
    BN_D_VAL            NVARCHAR(30)    NULL,        -- '69+5', '160+5'
    BN_VAL              NVARCHAR(30)    NULL,        -- '25' (sin el +D)
    BN_TOTAL            FLOAT           NULL,        -- BN+D sumado: 69+5=74
    ACERO_VAL           NVARCHAR(50)    NULL,
    STEEL_VAL           NVARCHAR(50)    NULL,
    ESPESOR_VAL         NVARCHAR(50)    NULL,
    MATERIAL_VAL        NVARCHAR(100)   NULL,
    TIPO_VAL            NVARCHAR(100)   NULL,
    BANDA_VAL           NVARCHAR(50)    NULL,
    CAMPOS_JSON         NVARCHAR(1000)  NULL,        -- JSON con todos los campos crudos

    -- ── Posición absoluta (coordenadas DXF) ──
    DXF_X               FLOAT           NULL,        -- centro del cajetín
    DXF_Y               FLOAT           NULL,
    BBOX_XMIN           FLOAT           NULL,
    BBOX_YMIN           FLOAT           NULL,
    BBOX_XMAX           FLOAT           NULL,
    BBOX_YMAX           FLOAT           NULL,

    -- ── Posición normalizada respecto al plano (0.0 a 1.0) ──
    -- Permite comparar posición relativa entre planos de distinto tamaño
    REL_X               FLOAT           NULL,        -- 0=izquierda, 1=derecha
    REL_Y               FLOAT           NULL,        -- 0=abajo, 1=arriba (DXF Y crece hacia arriba)
    REL_Y_IMG           FLOAT           NULL,        -- 0=arriba, 1=abajo (sistema imagen/pantalla)

    -- ── Zona semántica (grid 3x3) ──
    ZONA_H              NVARCHAR(10)    NULL,        -- 'IZQ' | 'CENTER' | 'DER'
    ZONA_V              NVARCHAR(10)    NULL,        -- 'TOP' | 'MID' | 'BOT'
    ZONA                NVARCHAR(20)    NULL,        -- 'TOP_IZQ', 'BOT_CENTER', etc.
    -- ZONA_INTERIOR: si el cajetín está dentro del contorno del vidrio (NULL = no determinado aún)
    ZONA_INTERIOR       BIT             NULL,

    -- ── Posición en píxeles para render ──
    PX_X                FLOAT           NULL,
    PX_Y                FLOAT           NULL,
    BBOX_PX_LEFT        FLOAT           NULL,
    BBOX_PX_TOP         FLOAT           NULL,
    BBOX_PX_W           FLOAT           NULL,
    BBOX_PX_H           FLOAT           NULL,
);
GO

CREATE INDEX IX_CAJETINES_PLANO  ON [AUTOMATA].[CAJETINES] (PLANO_ID);
CREATE INDEX IX_CAJETINES_ZONA   ON [AUTOMATA].[CAJETINES] (ZONA);
CREATE INDEX IX_CAJETINES_OFFSET ON [AUTOMATA].[CAJETINES] (OFFSET_VAL);
GO

-- =============================================================================
-- TEXTOS — Todos los textos extraídos del DXF (texto plano, cajetín o no)
-- Base para futuras lógicas de clasificación
-- =============================================================================
CREATE TABLE [AUTOMATA].[TEXTOS] (
    ID                  INT IDENTITY(1,1) PRIMARY KEY,
    PLANO_ID            INT             NOT NULL REFERENCES [AUTOMATA].[PLANOS](ID) ON DELETE CASCADE,

    TEXTO               NVARCHAR(500)   NOT NULL,
    TIPO_ENTIDAD        NVARCHAR(20)    NULL,        -- 'TEXT','MTEXT','ATTRIB'
    LAYER               NVARCHAR(100)   NULL,        -- layer DXF original
    LAYER_UPPER         NVARCHAR(100)   NULL,        -- layer en mayúsculas para búsquedas

    -- Clasificación semántica
    TIPO                NVARCHAR(20)    NULL,        -- 'RADIO','COTA','CAMPO_CAJ','VALOR_CAJ','LABEL','OTRO'
    VALOR_NUMERICO      FLOAT           NULL,        -- si el texto es un número o 'R50' → 50
    ES_RADIO            BIT             DEFAULT 0,   -- texto tipo 'R50', 'R6'
    ES_COTA             BIT             DEFAULT 0,   -- número grande de cota (>50, no OFFSET ni BN)
    ES_CAMPO_TEC        BIT             DEFAULT 0,   -- coincide con TECHNICAL_FIELDS
    CAJETIN_ID          INT             NULL,        -- si pertenece a un cajetín (FK opcional)

    -- Posición
    DXF_X               FLOAT           NULL,
    DXF_Y               FLOAT           NULL,
    REL_X               FLOAT           NULL,
    REL_Y               FLOAT           NULL,
    REL_Y_IMG           FLOAT           NULL,
);
GO

CREATE INDEX IX_TEXTOS_PLANO  ON [AUTOMATA].[TEXTOS] (PLANO_ID);
CREATE INDEX IX_TEXTOS_TIPO   ON [AUTOMATA].[TEXTOS] (TIPO);
CREATE INDEX IX_TEXTOS_LAYER  ON [AUTOMATA].[TEXTOS] (LAYER_UPPER);
GO

-- =============================================================================
-- RADIOS — Valores de radio extraídos (R6, R50, R70...)
-- Tabla propia porque son muy relevantes para comparación geométrica
-- =============================================================================
CREATE TABLE [AUTOMATA].[RADIOS] (
    ID          INT IDENTITY(1,1) PRIMARY KEY,
    PLANO_ID    INT     NOT NULL REFERENCES [AUTOMATA].[PLANOS](ID) ON DELETE CASCADE,
    TEXTO_ORIG  NVARCHAR(20) NULL,  -- 'R50', 'R6.5'
    VALOR       FLOAT   NOT NULL,   -- 50, 6.5
    LAYER       NVARCHAR(100) NULL,
    DXF_X       FLOAT   NULL,
    DXF_Y       FLOAT   NULL,
    REL_X       FLOAT   NULL,
    REL_Y       FLOAT   NULL,
    ZONA        NVARCHAR(20) NULL,
);
GO

CREATE INDEX IX_RADIOS_PLANO ON [AUTOMATA].[RADIOS] (PLANO_ID);
CREATE INDEX IX_RADIOS_VALOR ON [AUTOMATA].[RADIOS] (VALOR);
GO

-- =============================================================================
-- COTAS — Dimensiones lineales del plano (245, 827, 1163...)
-- =============================================================================
CREATE TABLE [AUTOMATA].[COTAS] (
    ID              INT IDENTITY(1,1) PRIMARY KEY,
    PLANO_ID        INT     NOT NULL REFERENCES [AUTOMATA].[PLANOS](ID) ON DELETE CASCADE,
    VALOR           FLOAT   NOT NULL,
    ORIENTACION     NVARCHAR(5)  NULL,   -- 'H' horizontal | 'V' vertical | NULL desconocida
    LAYER           NVARCHAR(100) NULL,
    DXF_X           FLOAT   NULL,
    DXF_Y           FLOAT   NULL,
    REL_X           FLOAT   NULL,
    REL_Y           FLOAT   NULL,
    ZONA            NVARCHAR(20) NULL,
);
GO

CREATE INDEX IX_COTAS_PLANO ON [AUTOMATA].[COTAS] (PLANO_ID);
CREATE INDEX IX_COTAS_VALOR ON [AUTOMATA].[COTAS] (VALOR);
GO

-- =============================================================================
-- IMAGENES_SAP — Imágenes asociadas en SAP para cada plano
-- =============================================================================
CREATE TABLE [AUTOMATA].[IMAGENES_SAP] (
    ID          INT IDENTITY(1,1) PRIMARY KEY,
    PLANO_ID    INT             NOT NULL REFERENCES [AUTOMATA].[PLANOS](ID) ON DELETE CASCADE,
    DOCUMENTO   NVARCHAR(100)   NULL,   -- 'M1761 006 005 A'
    RUTA_SAP    NVARCHAR(500)   NULL,   -- '\\192.168.2.2\Sapfiles\...'
    FECHA_BUSQUEDA DATETIME     DEFAULT GETDATE(),
    ENCONTRADA  BIT             DEFAULT 1,
);
GO

CREATE INDEX IX_IMAGENES_SAP_PLANO ON [AUTOMATA].[IMAGENES_SAP] (PLANO_ID);
GO

-- =============================================================================
-- SIMILITUD — Cache de scores de similitud entre pares de planos
-- Se recalcula cuando los planos cambian (HASH distinto)
-- =============================================================================
CREATE TABLE [AUTOMATA].[SIMILITUD] (
    ID                  INT IDENTITY(1,1) PRIMARY KEY,
    PLANO_A_ID          INT     NOT NULL REFERENCES [AUTOMATA].[PLANOS](ID),
    PLANO_B_ID          INT     NOT NULL REFERENCES [AUTOMATA].[PLANOS](ID),

    -- Score global y por dimensión (0.0 a 1.0)
    SCORE_TOTAL         FLOAT   NULL,   -- score ponderado final
    SCORE_CAJETINES     FLOAT   NULL,   -- similitud de valores OFFSET + BN+D por zona
    SCORE_RADIOS        FLOAT   NULL,   -- Jaccard sobre conjuntos de radios
    SCORE_COTAS         FLOAT   NULL,   -- similitud cotas principales
    SCORE_POSICION      FLOAT   NULL,   -- similitud posición relativa cajetines
    SCORE_ASPECT        FLOAT   NULL,   -- similitud de aspect ratio y dimensiones

    -- Detalle de qué coincide y qué no (JSON para mostrar en UI)
    DIFF_JSON           NVARCHAR(MAX) NULL,  -- {matches:[...], diffs:[...]}

    -- Número de cajetines emparejados
    CAJETINES_A         INT     NULL,
    CAJETINES_B         INT     NULL,
    CAJETINES_MATCH     INT     NULL,

    FECHA_CALCULO       DATETIME DEFAULT GETDATE(),
    VERSION_ALGORITMO   NVARCHAR(20) DEFAULT '1.0',

    CONSTRAINT UQ_SIMILITUD_PAR UNIQUE (PLANO_A_ID, PLANO_B_ID),
    CONSTRAINT CK_SIMILITUD_PAR CHECK (PLANO_A_ID < PLANO_B_ID) -- siempre A < B para no duplicar
);
GO

CREATE INDEX IX_SIMILITUD_A     ON [AUTOMATA].[SIMILITUD] (PLANO_A_ID, SCORE_TOTAL DESC);
CREATE INDEX IX_SIMILITUD_B     ON [AUTOMATA].[SIMILITUD] (PLANO_B_ID, SCORE_TOTAL DESC);
CREATE INDEX IX_SIMILITUD_SCORE ON [AUTOMATA].[SIMILITUD] (SCORE_TOTAL DESC);
GO

-- =============================================================================
-- VEHICULOS_CATALOGO — Catálogo de vehículos conocidos (manual o auto-poblado)
-- Para normalizar nombres y asociar marca/modelo/año
-- =============================================================================
CREATE TABLE [AUTOMATA].[VEHICULOS_CATALOGO] (
    ID              INT IDENTITY(1,1) PRIMARY KEY,
    NOMBRE_CARPETA  NVARCHAR(150)   NOT NULL UNIQUE,  -- 'SUZUKI JIMNY 2021'
    MARCA           NVARCHAR(100)   NULL,
    MODELO          NVARCHAR(100)   NULL,
    ANNO            NVARCHAR(10)    NULL,
    ACTIVO          BIT             DEFAULT 1,
    FECHA_REGISTRO  DATETIME        DEFAULT GETDATE(),
);
GO

-- =============================================================================
-- PIEZAS_CATALOGO — Catálogo de tipos de pieza (referencia fija)
-- =============================================================================
CREATE TABLE [AUTOMATA].[PIEZAS_CATALOGO] (
    CODIGO          NVARCHAR(5)     PRIMARY KEY,  -- '000', '009'
    NOMBRE          NVARCHAR(100)   NOT NULL,     -- 'Parabrisas', 'Posterior'
    DESCRIPCION     NVARCHAR(300)   NULL,
    ACTIVO          BIT             DEFAULT 1,
);
GO

INSERT INTO [AUTOMATA].[PIEZAS_CATALOGO] (CODIGO, NOMBRE) VALUES
('000','Parabrisas'),
('001','Lateral Delantero Izquierdo'),('002','Lateral Delantero Derecho'),
('003','Lateral Trasero Izquierdo'),  ('004','Lateral Trasero Derecho'),
('005','Ventilete Trasero Izquierdo'),('006','Ventilete Trasero Derecho'),
('007','Cabina Trasera Izquierda'),   ('008','Cabina Trasera Derecha'),
('009','Posterior'),                  ('010','Techo Solar Delantero'),
('011','Lateral Extendido Izquierdo'),('012','Lateral Extendido Derecho'),
('013','Posterior Izquierdo'),        ('014','Posterior Derecho'),
('015','Claraboya Izquierda'),        ('016','Claraboya Derecha'),
('017','Mirilla'),                    ('018','Probeta'),
('019','Ventilete Delantero Izquierdo'),('020','Ventilete Delantero Derecho'),
('021','Cabina Delantera Izquierda'), ('022','Cabina Delantera Derecha'),
('023','Cabina Superior Izquierda'),  ('024','Cabina Superior Derecha'),
('025','Techo Solar B'),              ('026','Parabrisas Derecho'),
('027','Parabrisas Izquierdo'),       ('028','Lateral Secundario Derecho'),
('029','Lateral Secundario Izquierdo'),('030','Particion'),
('031','Arquitectura'),               ('034','Porthole 1'),
('035','Porthole 2'),                 ('036','Porthole 3'),
('037','Porthole 4'),                 ('040','Pummel'),
('085','Posterior Secundario'),       ('087','Techo Solar Centrico'),
('088','Techo Solar D'),              ('090','Techo Solar Panoramico'),
('091','Probeta 2'), ('092','Probeta 3'), ('093','Probeta Especial'),
('094','Probeta 4'), ('095','Kit Opaco'), ('096','Probeta 5'),
('097','Probeta 6'),
('110','Techo Solar A Paquete'),      ('125','Techo Solar B Paquete'),
('187','Techo Solar C Paquete'),      ('190','Techo Solar Panoramico Paquete');
GO

PRINT 'Schema AUTOMATA creado correctamente en AGP_Ingenieria';
GO
