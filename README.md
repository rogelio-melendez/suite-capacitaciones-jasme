# App JASME Capacitación — versión en línea (100% gratis, multiusuario)

Esta versión vive en internet: tu equipo entra desde cualquier computadora o
celular, en cualquier momento, con su propio usuario y contraseña. No hay
que dejar ninguna computadora encendida.

## Las 4 piezas gratuitas que la hacen posible

| Pieza | Para qué sirve | ¿Pide tarjeta? |
|---|---|---|
| **GitHub** | Guarda el código de la app | No |
| **Streamlit Community Cloud** | Corre la app 24/7 para que la vean desde cualquier lugar | No |
| **Supabase** | Guarda usuarios/contraseñas y las claves de examen de forma permanente | No |
| **Groq** | El motor de IA que genera temarios, contenido, dinámicas y exámenes | No |

Ninguna cobra nada en el uso normal de un equipo de 2-5 personas. Más abajo
hay una sección de límites para que sepas qué esperar.

---

## Instalación paso a paso (se hace una sola vez)

### Paso 1 — Crear el repositorio en GitHub

1. Ve a **github.com**, crea una cuenta gratis si no tienes.
2. Botón **+** (arriba a la derecha) → **New repository**.
3. Nómbralo, por ejemplo, `jasme-capacitacion`. Marca **Private**.
4. Descomprime el `jasme_exam_app.zip` que te dieron, y dentro del
   repositorio nuevo: **Add file → Upload files**, arrastra TODO lo que
   está dentro de la carpeta `jasme_app` (no la carpeta misma).
5. Commit changes.

### Paso 2 — Crear el proyecto en Supabase

1. Ve a **supabase.com** → **Start your project** → crea cuenta gratis
   (puedes usar tu cuenta de GitHub para entrar más rápido).
2. **New project**. Ponle un nombre y una contraseña de base de datos
   (guárdala, aunque no la vuelves a necesitar seguido). Elige la región
   más cercana a México. Espera 1-2 minutos mientras se crea.
3. En el menú izquierdo, ve a **SQL Editor** → **New query**.
4. Abre el archivo `supabase_schema.sql` (viene en tu zip), copia todo su
   contenido, pégalo ahí, y dale **Run**. Esto crea la tabla donde se
   guardan las claves de examen.
5. Ve a **Settings** (ícono de engrane) → **API**. Ahí vas a ver y vas a
   necesitar copiar tres cosas (los siguientes pasos te dicen dónde
   pegarlas):
   - **Project URL**
   - **anon public** key
   - **service_role** key (dale clic en "Reveal" para verla completa — es
     secreta, no la compartas)

### Paso 3 — Crear tu clave gratis de Groq (el motor de IA)

1. Ve a **console.groq.com** → crea cuenta gratis (con Google es más rápido).
2. Ve a **API Keys** → **Create API Key** → ponle un nombre → cópiala (solo
   se muestra una vez completa).

### Paso 4 — Publicar la app en Streamlit Community Cloud

1. Ve a **share.streamlit.io** → **Sign in with GitHub** (misma cuenta del
   Paso 1).
2. **New app** → elige tu repositorio `jasme-capacitacion` → Branch `main`
   → **Main file path**: `app.py`.
3. Antes de darle a Deploy, abre **Advanced settings** → en el cuadro de
   **Secrets**, pega exactamente esto, reemplazando cada valor por el tuyo
   (sin borrar las comillas):

   ```toml
   SUPABASE_URL = "https://tu-proyecto.supabase.co"
   SUPABASE_ANON_KEY = "tu-anon-key-aqui"
   SUPABASE_SERVICE_ROLE_KEY = "tu-service-role-key-aqui"
   GROQ_API_KEY = "tu-groq-key-aqui"
   ```
4. **Deploy**. Espera 2-5 minutos (la primera vez tarda más porque instala
   todo). Te dará una URL como `https://jasme-capacitacion.streamlit.app`.

### Paso 5 — Crear tu primer usuario administrador

Como no hay registro público, el primerísimo usuario se crea directo en
Supabase (después de este, ya usas el panel normal de la app para todos
los demás):

1. En Supabase, ve a **Authentication** → **Users** → **Add user** →
   **Create new user**.
2. Pon tu correo y una contraseña. Marca **Auto Confirm User** (importante,
   si no, te va a pedir confirmar por correo y no tenemos ese paso configurado).
3. Después de crearlo, dale clic al usuario que acabas de crear, busca la
   sección de metadata (**User Metadata** / **Raw user meta data**), y
   edítala para que diga:
   ```json
   {"role": "admin"}
   ```
   Guarda.
4. Entra a tu app con ese correo y contraseña — ya deberías ver la opción
   "⚙️ Administrar usuarios" en el menú. De aquí en adelante, todos los
   usuarios nuevos (incluyendo otros admins) los creas desde ahí, dentro de
   la app, sin volver a tocar Supabase directamente.

### Paso 6 (opcional) — Recuperar tus exámenes de NOM-004 y NOM-026

Si ya tenías esas dos claves capturadas (vienen en `config/*.json` dentro
del zip), puedes copiarlas a Supabase sin volver a escribirlas:

1. En tu computadora, dentro de la carpeta del proyecto:
   ```
   pip install supabase
   python seed_configs.py https://tu-proyecto.supabase.co tu-service-role-key-aqui
   ```
2. Listo — ya aparecen en "Calificar exámenes" dentro de la app.

---

## Uso diario (para ti y tu equipo)

Nada cambia respecto a lo que ya conocías, excepto que ahora entran por una
URL con su correo/contraseña en vez de abrir una terminal:

- **Calificar exámenes**: hojas de burbujas escaneadas/fotografiadas +
  Excel de Forms → Excel final con formato JASME.
- **Crear / editar clave de un examen**: captura preguntas y respuesta
  correcta, genera la hoja de burbujas para imprimir.
- **Crear curso de capacitación**: sube tu material, sigue el asistente de
  6 pasos (temario → objetivo → contenido → dinámicas → exámenes → generar).
- **⚙️ Administrar usuarios** (solo tú y quien más nombres admin): crear/
  eliminar cuentas de tu equipo, cambiar tu contraseña.

## Límites que debes conocer (para que nada te sorprenda)

- **Streamlit Community Cloud**: si nadie visita la app por varios días,
  se "duerme" y la próxima visita tarda ~30 segundos en despertar. No se
  pierde nada guardado.
- **Supabase (plan gratis)**: pausa el proyecto si pasan **7 días sin
  ninguna actividad**. Se reactiva solo, con la siguiente visita a la app
  (tarda un poco más esa vez). Nada se borra.
- **Groq (plan gratis)**: tiene un límite de solicitudes por día, generoso
  para 2-5 personas generando cursos ocasionalmente. Si algún día lo
  alcanzan, el mensaje de error lo dice claro y se resetea al día
  siguiente.
- **Contenido generado por IA**: sigue siendo una síntesis automática —
  por eso cada paso del asistente te deja revisar y corregir antes de
  continuar. Groq usa un modelo más grande y capaz que el que probamos
  localmente, así que la calidad debería notarse mejor.

## Actualizar la app en el futuro

Como el código vive en GitHub, para actualizar algo (un cambio que yo te
dé, o que tú edites): entra a tu repositorio en github.com, edita el
archivo ahí mismo (ícono de lápiz) o sube el archivo nuevo, y Streamlit
Cloud vuelve a publicar la app sola en 1-2 minutos.

## Estructura del proyecto

| Archivo | Qué hace |
|---|---|
| `app.py` | La interfaz principal (los modos + login). |
| `auth.py` | Login y panel de administración de usuarios (Supabase Auth). |
| `supabase_client.py` | Toda la comunicación con Supabase (usuarios + claves de examen). |
| `groq_client.py` | Conexión con la IA en la nube (Groq, gratis). |
| `course_wizard.py` / `course_ai.py` | El asistente de 6 pasos para crear cursos. |
| `bubble_sheet.py` | Generador y lector de hojas de burbujas (sin IA). |
| `course_builder.py` | Arma el curso reutilizando la plantilla JASME clásica. |
| `freeform_builder.py` / `deck_style.py` | Arma el curso desde cero, con cualquier paleta de colores. |
| `report_builder.py` / `jasme_style.py` | Arman el Excel de resultados con el formato JASME. |
| `forms_parser.py` | Lee el Excel de Google/Microsoft Forms. |
| `content_extractor.py` | Lee PDF/Word/TXT para dárselo a la IA. |
| `supabase_schema.sql` | El SQL para crear la tabla de claves de examen (Paso 2). |
| `seed_configs.py` | Script opcional para migrar tus claves viejas a Supabase (Paso 6). |
| `assets/` | El logo y la plantilla JASME. |

Si algo deja de funcionar, mándame el mensaje de error exacto (y en qué
paso pasó) y seguimos desde ahí.
