# Evidencia Técnica · PRB-52

## PRB-52 · [P-04] Migración de datos reales: carta, precios, fotos, 13 mesas, usuarios y PIN

### 1. Cumplimiento de Reglas Arquitectónicas (D7 y D8)
- **Regla D7 (`docs/db/DDL-OWNERSHIP.md`)**:
  - Modelos `Rol` y `Usuario` declarados con `managed = False` en `catalogo/models.py` (`0007_rol_usuario.py`).
  - Cero alteraciones de DDL fuera de `db/schema.sql`.
- **Regla D8 (`docs/db/D8-PASSWORD-HASHING.md`) y Seguridad R9 / PRB-67**:
  - `bcrypt==5.0.0` fijado en `requirements.txt`.
  - Tanto `usuario.clave_hash` como `usuario.pin_hash` (PIN numérico de 4 dígitos) utilizan exclusivamente **BCrypt cost factor 10 (`$2b$10$...`)**, directamente verificables por `BCryptPasswordEncoder` en Spring Boot y `bcrypt.checkpw()` en Django.
  - Eliminación / saneamiento automático de la cuenta demo `admin_test` y prohibición explícita de la clave débil `password123`.

---

### 2. Inventario Oficial Migrado e Idempotente (`db/seeds_produccion.sql` + `seed_produccion`)

1. **4 Roles Operativos Canónicos (`rol`)**:
   - `ADMIN`, `MOZO`, `COCINERO`, `CAJERO`.
2. **5 Cuentas Operativas Base con Contraseña Segura y PIN de 4 Dígitos (`usuario`)**:
   - `admin_casablanca` (`ADMIN`) · Hash BCrypt verificado
   - `cajero_01` (`CAJERO`) · Hash BCrypt verificado
   - `mozo_01` (`MOZO` · Piso 1) · Hash BCrypt verificado
   - `mozo_02` (`MOZO` · Piso 2) · Hash BCrypt verificado
   - `cocinero_01` (`COCINERO` · Cocina / Barra Fría) · Hash BCrypt verificado
   - Gestión y rotación en vivo disponible en `/personal/` (alta de personal, cambio de rol/clave/PIN y desbloqueo de cuentas tras intentos fallidos).
3. **5 Categorías Oficiales y 15 Platos Marinos Reales con Precios y Fotos PNG Locales (`categoria`, `producto`)**:
   - **Entradas Marinas**: Leche de Tigre Clásica (`S/ 25.00`), Causa de Pulpa de Cangrejo (`S/ 32.00`), Choros a la Chalaca (`S/ 24.00`).
   - **Ceviches y Tiraditos**: Ceviche Clásico Casa Blanca (`S/ 48.00`), Ceviche Mixto Especial (`S/ 54.00`), Tiradito en Crema de Ají Amarillo (`S/ 49.00`), Ceviche de Conchas Negras (`S/ 56.00`).
   - **Platos de Fondo**: Jalea Mixta Real (`S/ 58.00`), Arroz con Mariscos (`S/ 50.00`), Parihuela Concentrada (`S/ 55.00`), Corvina a lo Macho (`S/ 62.00`).
   - **Bebidas**: Chicha Morada de la Casa 1 L (`S/ 16.00`), Limonada Frozen 1 L (`S/ 18.00`).
   - **Postres**: Suspiro a la Limeña (`S/ 14.00`), Picarones con Miel de Chancaca (`S/ 15.00`).
   - Todos servidos offline en LAN desde `catalogo/static/catalogo/img/platos/*.png` (`320x240` RGB PNG).
4. **13 Mesas Reales en 2 Pisos (`mesa`)**:
   - **Primer piso (Mesas 1–7)**: Salón (`1–3`, cap. 4), Familiar (`4–5`, cap. 6), Barra Marina (`6–7`, cap. 2).
   - **Segundo piso (Mesas 8–13)**: Salón (`8–10`, cap. 4), Vista Mar (`11–12`, cap. 6), Terraza VIP (`13`, cap. 8).

---

### 3. Resultados de Calidad y Base de Datos Real (PostgreSQL 18 `casablanca`)

```text
[PG OK] V2__produccion.sql + seeds_produccion.sql (x2) aplicados con exito en casablanca
Auditoría PRB-52 OK: 4 roles, 5 usuarios con PIN BCrypt, 15/15 platos oficiales con foto y 13/13 mesas verificadas.
Seeds PRB-52 aplicados: roles +0, usuarios +0/~0, platos +0/~0, mesas +0/~0.
Auditoría PRB-52 OK: 4 roles, 5 usuarios con PIN BCrypt, 15/15 platos oficiales con foto y 13/13 mesas verificadas.

manage.py test -> 49 passed (0 fallos)
makemigrations --check --dry-run -> No changes detected
coverage -> 84%+ (catalogo/*)
flake8 -> 0 errores
black --check -> 0 archivos pendientes
```
