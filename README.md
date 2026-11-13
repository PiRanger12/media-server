# 🎬 Media Server

Servidor multimedia casero para una computadora con **Ubuntu**. Sirve para administrar y reproducir **videos** y **música** desde cualquier dispositivo de la red local.

| Servicio | Para qué sirve | Puerto |
|---|---|---|
| **Jellyfin** | Reproducir películas, series y videos, con portadas, subtítulos y transcodificación | `8096` |
| **Navidrome** | Reproducir música, con álbumes, artistas y playlists. Es compatible con apps Subsonic | `4533` |
| **Media Panel** (propio) | Subir, organizar, renombrar, mover y borrar archivos, editar etiquetas y lanzar escaneos | `8080` |

```
                ┌──────────── Servidor Ubuntu (Docker) ────────────┐
 Navegador ───► │  Media Panel :8080 ──escribe──►  /srv/media/      │
 (PC, celular)  │        │                         ├── videos/ ◄─── Jellyfin  :8096 (solo lectura)
                │        └─ avisa "escanea" ──►    └── music/  ◄─── Navidrome :4533 (solo lectura)
                └───────────────────────────────────────────────────┘
```

## Funciones del panel

- 📂 **Explorador** de las bibliotecas `videos/` y `music/`, con carpetas, migas de pan y filtro.
- ⬆️ **Subida** con arrastrar y soltar y barra de progreso. Admite archivos de varios GB porque el cuerpo de la petición se escribe directo al disco.
- ✏️ Renombrar, 📦 mover y 🗑️ borrar archivos y carpetas, y crear carpetas nuevas.
- 🏷️ **Edición de etiquetas** de música (título, artista, álbum, género, año, pista): MP3, FLAC, OGG, M4A, etc.
- ℹ️ **Información técnica** de los videos (resolución, códecs, pistas de audio, subtítulos) con `ffprobe`, más **miniaturas** automáticas.
- ▶️ **Vista previa** de audio y video en el navegador.
- 🔄 **Escaneo automático**: el panel vigila las carpetas y, 15 s después del último cambio, pide a Jellyfin o Navidrome que reescaneen. También hay un botón para escanear a mano.
- 🔒 Acceso con contraseña. Las rutas están confinadas a cada biblioteca, sin path traversal, y cada biblioteca solo acepta sus extensiones.

## Instalación

Requisitos: Ubuntu 22.04 o 24.04 con acceso a Internet. El script instala Docker si hace falta.

```bash
git clone https://github.com/<tu-usuario>/media-server.git
cd media-server
chmod +x install.sh
sudo ./install.sh
```

El script:
1. Instala Docker y Docker Compose.
2. Crea `.env` con tu UID/GID, una `SECRET_KEY` aleatoria y la contraseña del panel que escribas.
3. Crea `/srv/media/videos` y `/srv/media/music`. Puedes cambiar la ruta en `MEDIA_ROOT` dentro de `.env`.
4. Si `ufw` está activo, abre los puertos **solo para tu red local**.
5. Levanta los tres contenedores.

> 💡 Si quieres usar un disco aparte para los archivos, móntalo antes (por ejemplo en `/mnt/disco`) y pon `MEDIA_ROOT=/mnt/disco/media` en `.env`.

## Configuración inicial (una sola vez)

### 1. Jellyfin → `http://IP:8096`
1. Sigue el asistente: idioma, usuario administrador y contraseña.
2. **Agregar biblioteca**: tipo *Películas* o *Series*, carpeta `/media/videos`. Puedes crear subcarpetas como `videos/Peliculas` y `videos/Series` y hacer una biblioteca para cada una.
3. Ve a **Panel de control → Claves de API → ＋**, crea una llamada `media-panel` y copia la clave.

### 2. Navidrome → `http://IP:4533`
1. La primera vez te pide crear el usuario administrador. Anota el usuario y la contraseña.
2. La música se lee de `/music`. No hay nada más que configurar.

### 3. Conectar el panel
Edita `.env`:
```env
JELLYFIN_API_KEY=la-clave-que-copiaste
NAVIDROME_USER=admin
NAVIDROME_PASSWORD=tu-contraseña-de-navidrome
```
y reinicia el panel:
```bash
docker compose up -d panel
```
En la barra lateral del panel, los dos servicios deben aparecer **En línea** y sin el aviso “falta configurar”.

## Cómo organizar los archivos

Jellyfin y Navidrome identifican mejor el contenido si sigues estas convenciones:

```
videos/
├── Peliculas/
│   └── Interestelar (2014)/
│       ├── Interestelar (2014).mkv
│       └── Interestelar (2014).es.srt
└── Series/
    └── Dark/
        └── Season 01/
            └── Dark S01E01.mkv
music/
└── Artista/
    └── Álbum (Año)/
        ├── 01 - Canción.flac
        └── cover.jpg
```

En la música, lo que más importa son las **etiquetas** (artista, álbum, pista), y las puedes corregir desde el panel con 🏷️.

## Comandos útiles

```bash
docker compose ps                 # estado de los contenedores
docker compose logs -f panel      # ver logs del panel
docker compose pull && docker compose up -d --build   # actualizar todo
docker compose down               # detener
```

Los contenedores se reinician solos al prender el servidor (`restart: unless-stopped`).

## Desarrollo local del panel

```bash
cd panel
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
MEDIA_DIR=/tmp/media DATA_DIR=/tmp/panel PANEL_PASSWORD=dev uvicorn app.main:app --reload --port 8080
pytest                            # pruebas
```
La documentación interactiva de la API está en `http://localhost:8080/api/docs`.

### Estructura

```
panel/app/
├── main.py       # rutas FastAPI (auth, archivos, subida, metadatos, escaneo)
├── storage.py    # operaciones de archivos confinadas a cada biblioteca
├── metadata.py   # etiquetas (mutagen), ffprobe y miniaturas (ffmpeg)
├── scanners.py   # API de Jellyfin y Subsonic de Navidrome
├── watcher.py    # escaneo automático con watchfiles
└── static/       # frontend (HTML + CSS + JS sin frameworks)
```

## Extras opcionales

- **Aceleración por hardware** en Jellyfin (Intel/AMD): descomenta `devices: /dev/dri` en `docker-compose.yml` y actívala en *Panel de control → Reproducción*.
- **Apps móviles**: para video, Jellyfin para Android/iOS. Para música, cualquier cliente Subsonic (Symfonium, substreamer, Tempo) apuntando a `http://IP:4533`.
- **IP fija**: reserva la IP del servidor en tu router (DHCP estático) para que las direcciones no cambien.
