# Bot de aviso: visa Work and Holiday 462 (Argentina)

Revisa la página de Home Affairs **cada 15 minutos, las 24 horas**, y te manda una notificación push al celular **apenas cambia** el estado de Argentina. Cuando pasa a **OPEN**, te avisa con prioridad máxima en cada chequeo hasta que lo apagues.

### Cómo se asegura de leer la versión más reciente

Home Affairs a veces sirve copias viejas de la página según desde dónde se la consulte. Para evitarlo, el bot:

1. Abre la página con un **navegador real (Chrome)**, igual que vos, sin caché y con una dirección distinta en cada consulta.
2. La descarga también de forma directa, como segunda fuente.
3. Lee el **"Last updated"** de cada copia y usa la más nueva.
4. Si recibe una copia **más vieja** que la última que ya vio, la descarta y no cambia nada.
5. En cada notificación te muestra qué "Last updated" leyó, así podés compararla con lo que ves en el navegador.

Es gratis: corre en **GitHub Actions** y las notificaciones llegan por **ntfy** (una app gratuita, no hace falta crear cuenta).

## 1. Instalá ntfy en el celular (2 minutos)

1. Descargá **ntfy** desde Play Store o App Store.
2. Tocá **+** / "Subscribe to topic".
3. Inventá un nombre de canal largo y difícil de adivinar, por ejemplo `visa462-agus-k8x3q9`. Cualquiera que sepa el nombre puede leer o mandar mensajes a ese canal, así que no uses algo obvio.
4. En Android: en la configuración de la app, desactivá la optimización de batería para ntfy. Así las alertas llegan aunque el celular esté en reposo (sobre todo de madrugada).
5. En los ajustes del canal podés elegir un sonido fuerte para las notificaciones de prioridad máxima.

## 2. Creá el repositorio en GitHub

1. Entrá a https://github.com/new, ponele un nombre (por ejemplo `visa-462-bot`) y creá el repo como **público**. Como ahora usa un navegador real, cada chequeo tarda más de un minuto, y en un repo privado se superarían los 2000 minutos gratis por mes. En los repos públicos los minutos son ilimitados. Lo único visible es el código y el último estado; el nombre de tu canal de ntfy queda guardado como secreto.
2. Subí estos archivos respetando las carpetas:
   - `check_visa.py`
   - `.github/workflows/visa-462.yml`
   - `README.md` (opcional)

   Desde la web: "Add file" → "Upload files" y arrastrá todo. Si la carpeta `.github` no se sube, creá el archivo a mano con "Add file" → "Create new file" y escribí `.github/workflows/visa-462.yml` como nombre.

## 3. Guardá el nombre del canal como secreto

En el repo: **Settings → Secrets and variables → Actions → New repository secret**

- Name: `NTFY_TOPIC`
- Secret: el nombre de canal que inventaste en el paso 1

## 4. Dale permiso de escritura al workflow

**Settings → Actions → General → Workflow permissions** → marcá **Read and write permissions** → Save.

(El bot guarda el último estado en `state.json` dentro del repo para saber si cambió.)

## 5. Probalo

**Actions → Vigilar visa 462 → Run workflow** (dejá tildado "Enviar notificación de prueba").

En menos de un minuto te tienen que llegar al celular:
- "🧪 Prueba bot visa 462 — Estado de Argentina: PAUSED — Versión leída: Last updated …"
- "✅ Bot visa 462 activo"

**Comprobá que la fecha de "Versión leída" coincida con el "Last updated" que ves al pie de la página en tu navegador.** Si coincide, ya está funcionando solo.

## Qué notificaciones vas a recibir

| Situación | Notificación | Prioridad |
|---|---|---|
| Argentina pasa a OPEN | 🇦🇺 ¡ABRIÓ la visa 462! con botón para ir a la página de la visa | Máxima (se repite cada 15 min mientras siga abierta) |
| Cualquier otro cambio (por ejemplo PAUSED → CLOSED) | Visa 462 Argentina: PAUSED → CLOSED | Alta |
| La página falla o cambia el formato | ⚠️ Bot visa 462: error | Normal (una sola vez hasta que se arregle) |
| Una vez por semana | "Sigo vigilando": solo confirma que el bot está vivo. **No reemplaza** a los avisos de cambio, que son inmediatos. | Mínima (silenciosa) |

## Ajustes

- **Dejar de recibir el aviso repetido cuando ya aplicaste:** Actions → Vigilar visa 462 → "…" → **Disable workflow**.
- **Que avise una sola vez al abrir** (en vez de repetir): en el `.yml`, agregá `REMIND_WHILE_OPEN: "0"` debajo de `COUNTRY: Argentina`.
- **Frecuencia:** línea `cron` del `.yml`. GitHub puede demorar las ejecuciones programadas 5–20 minutos en horarios de mucho uso; no hay forma de garantizar menos que eso en el plan gratis.
- **Otro país:** cambiá `COUNTRY: Argentina` por el nombre tal como aparece en la tabla (por ejemplo `Uruguay`).

## Probar en tu computadora (opcional)

```bash
NTFY_TOPIC=tu-canal python3 check_visa.py
```

Necesita Python 3.10+ y Playwright (`pip install playwright && python -m playwright install chromium`).

## Limitaciones a tener en cuenta

- La propia página aclara que los cambios pueden tardar hasta 48 horas en publicarse, y el cupo suele llenarse rápido. El bot te avisa en cuanto la página cambia, pero conviene tener la cuenta de ImmiAccount creada y los documentos listos de antemano.
- Si Home Affairs bloquea los servidores de GitHub o cambia el diseño de la tabla, vas a recibir la notificación de error. En ese caso, revisá la pestaña Actions para ver el detalle.
