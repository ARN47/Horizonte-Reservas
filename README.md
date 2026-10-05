# Biblioteca Horizonte – MVP de reservas

Aplicación web para que docentes soliciten proyectores y notebooks, y que Lucía (bibliotecaria) confirme o rechace.
**Regla central:** solo puede haber 1 reserva CONFIRMADA por recurso + fecha + módulo (se valida en el servicio y también con un índice único en la base de datos).

## Requisitos
- Python 3.10 o superior

## Cómo ejecutarlo
```bash
python -m venv venv
# Windows: venv\Scripts\activate      Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Abrir http://127.0.0.1:5000

## Usuarios de prueba
| Usuario | Clave | Rol |
|---|---|---|
| lucia | lucia123 | Bibliotecaria |
| ana | ana123 | Docente |
| marcos | marcos123 | Docente |
| sofia | sofia123 | Docente |

## Pruebas
```bash
python -m unittest -v
```

## Estructura
- `app.py`: servicio (API REST), reglas de negocio y base SQLite.
- `static/index.html`: interfaz.
- `test_app.py`: pruebas automáticas.
- `biblioteca.db`: se crea sola al primer arranque (no se sube a Git).

## Contrato de la API (resumen)
| Método | Ruta | Quién | Qué hace |
|---|---|---|---|
| POST | /api/login | todos | Inicia sesión |
| GET | /api/recursos | logueado | Recursos y módulos |
| POST | /api/solicitudes | docente | Crea solicitud (PENDIENTE) |
| GET | /api/solicitudes?estado= | logueado | Docente: las suyas. Lucía: todas |
| POST | /api/solicitudes/{id}/confirmar | Lucía | Confirma (409 si ya hay una confirmada igual) |
| POST | /api/solicitudes/{id}/rechazar | Lucía | Rechaza |
| GET | /api/solicitudes/{id}/historial | dueño o Lucía | Historial de estados |
| GET | /api/reservas?recurso_id=&fecha= | logueado | Reservas confirmadas |

Estados: `PENDIENTE`, `CONFIRMADA`, `RECHAZADA`. Errores: `{"error": "mensaje"}` con código 400/401/403/404/409.

## Supuestos
- 6 módulos horarios (editables en `MODULOS` de `app.py`).
- Recordatorios por correo: fuera del MVP (van al Product Backlog).
- Definir `SECRET_KEY` como variable de entorno si se despliega fuera de clase.
