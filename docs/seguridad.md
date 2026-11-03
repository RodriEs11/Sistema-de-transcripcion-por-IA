# Seguridad y privacidad

## Datos que maneja el sistema

| Dato | Dónde vive | Sale de la PC servidor |
|---|---|---|
| Audios de dictados | `Audios_nuevos/`, cola cifrada de la app | Solo en tránsito desde las PC del trabajo (HTTPS) |
| Transcripciones e informes | `Informes/` | Solo hacia la interfaz de una PC autenticada |
| Nombre del paciente | `<caso>.paciente.json` | Solo para mostrar en la lista; **nunca va a la IA ni al informe** |
| Ejemplos aprendidos | `ejemplos/` | No |
| Plantillas y notas de médicos | `conocimiento/` | No |
| Contraseñas y llaves | `acceso_remoto.json` y `usuarios.json` (hashes PBKDF2), DPAPI en cada PC | No |
| Sesiones abiertas | `sesiones.json` (solo la huella SHA-256 de cada sesión: no sirve para entrar) | No |
| Estilo de cada transcriptor | `conocimiento/usuarios/<clave>/` | No |
| Registros | `registros/` | No |
| Huellas de voz de los médicos | `voces/huellas.json`, `<caso>.voz.json` | No (no permiten reconstruir la voz ni lo dictado) |

Todo el reconocimiento de voz y la generación con IA se ejecutan **en la PC servidor** (Whisper y Ollama locales):
ningún dato clínico se envía a servicios de IA externos.

## Qué no contiene este repositorio

El [`.gitignore`](../.gitignore) excluye: datos de pacientes y derivados (`Informes/`, `Audios_nuevos/`, `Dataset/`,
`ejemplos/`, `referencias/`, `resultados/`, `registros/`, audios y documentos de Office), la base de conocimiento
real (`conocimiento/`, con nombres de profesionales), secretos (`acceso_remoto.json`, `usuarios.json`, `sesiones.json`,
`cliente/conexion.json`),
configuración local (`configuracion.json`), binarios (`*.exe`, `*.dll`, `cloudflared.exe`), respaldos y entornos virtuales.

Antes de cada *commit* conviene revisar `git status` y, ante la duda, buscar nombres propios o direcciones:

```bash
git grep -nE "trycloudflare\.com/|ntfy\.sh/[a-z0-9]{8,}|Dra?\. [A-Z]"
```

## Superficie expuesta

Solo la interfaz web, a través del túnel de Cloudflare. Protecciones:

- **Autenticación por PC**: llave *Bearer* por PC vinculada, o cookie de sesión; contraseña con PBKDF2 y sal.
- **Transcriptores** (si existen): usuario y contraseña propios, también en la PC del servidor; la llave de una PC
  sola ya no da acceso a los informes. Desactivar a alguien o restablecer su contraseña cierra sus sesiones.
- **Fuerza bruta**: 5 intentos fallidos bloquean 10 minutos; cada intento queda registrado.
- **Códigos de un solo uso** (60 s) para abrir la interfaz desde la app.
- **Cookies** `HttpOnly`, `Secure`, `SameSite=Strict`; la del panel está atada a la PC que la obtuvo.
- **Panel de administración**: por defecto solo desde `127.0.0.1` con `Host` local (evita *DNS rebinding*),
  sin encabezados de Cloudflare; los POST exigen `X-Panel: 1` y `Origin` de la misma página (evita CSRF).
- **Validación de nombres** de caso y de rutas: las descargas de la app solo sirven archivos del manifiesto
  (`../servidor.py`, `acceso_remoto.json` y variantes devuelven 404).
- **Permisos de borrado**: cada PC solo borra los casos que envió.
- **Sin caché**: todas las respuestas llevan `Cache-Control: no-store`.
- **Actualizaciones de la app**: cada archivo se verifica con SHA-256 y el `.exe` nuevo pasa una autoprueba antes
  de instalarse; si falla, se vuelve a la versión anterior.

## Riesgos conocidos

- El túnel rápido de Cloudflare no tiene disponibilidad garantizada y su dirección es pública (aunque aleatoria):
  la seguridad depende de la autenticación, no del secreto de la dirección.
- Si alguien obtiene el nombre del canal de ntfy, puede conocer la dirección del túnel (no acceder sin credenciales).
- El sistema es una **ayuda para transcribir**: todo informe debe ser leído completo por una persona antes de usarse.

## Reportar un problema de seguridad

Escribir en privado al autor (ver [LICENSE](../LICENSE)). No abrir *issues* públicos con detalles de vulnerabilidades.
