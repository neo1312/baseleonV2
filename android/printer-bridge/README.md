# Ferre Impresora - Puente Bluetooth (tablet)

App Android nativa que consulta la cola de impresión del VPS y envía los bytes
**ESC/POS** a la impresora térmica 58 mm por **Bluetooth Classic SPP**. Corre en
segundo plano (servicio en primer plano), así que imprime aunque el POS esté cerrado.

## Cómo funciona

```
POS (Chrome) --POST--> VPS Django  /pos/print-jobs/   (crea el trabajo)
                                 ▲
Esta app (servicio) -------------┘  GET /pos/print-jobs/pending/
   -> escribe los bytes al socket SPP de la impresora
   -> POST /pos/print-jobs/<id>/ack/
```

## Requisitos

- Tablet **Android** (API 24+), Chrome no es necesario para imprimir.
- Impresora 58 mm emparejada en **Ajustes → Bluetooth** (PIN `1234`).
- Certificado del VPS: ya viene empaquetado en `app/src/main/res/raw/ferre_cert.pem`
  (copia de `ssl/cert.pem`). Si cambia el certificado del servidor, reemplázalo y recompila.

## Compilar el APK

### Opción A - Android Studio (recomendado)
1. Abre esta carpeta `android/printer-bridge/` en Android Studio.
2. Deja que sincronice Gradle (genera el wrapper si hace falta).
3. `Build → Build Bundle(s) / APK(s) → Build APK(s)`.
4. APK en `app/build/outputs/apk/debug/app-debug.apk`.

### Opción B - línea de comandos
```bash
cd android/printer-bridge
gradle wrapper            # solo la primera vez
./gradlew assembleDebug
```

## Instalar en la tablet

1. Copia `app-debug.apk` a la tablet (USB, Google Drive, etc.).
2. Actívala: Ajustes → Seguridad → Fuentes desconocidas / Instalar apps desconocidas.
3. Abre el APK e instálala.

## Configurar

1. Abre la app **Ferre Impresora**.
2. Pega la **URL base** del sistema de esa tienda (ej. `https://5.75.162.179`
   o `http://5.75.162.179:8087`).
3. Pega el **Token** (`PRINT_API_TOKEN` de `.env.prod` / `clone/.env.clone`).
4. Elige la **impresora emparejada** de la lista.
5. **Guardar** → **Probar impresión**.
6. **Iniciar** (y deja activado "Iniciar al encender la tablet").

## Notas

- Android 12+: concede permisos de **Dispositivos cercanos** (Bluetooth).
- En algunos fabricantes (Xiaomi, Huawei) habilita el **autoarranque** y desactiva
  la **optimización de batería** para que el servicio no se detenga.
- Si el servidor usa un certificado público (dominio con Let's Encrypt), reemplaza
  `ferre_cert.pem` o bórralo; la app también confía en las CA del sistema.
