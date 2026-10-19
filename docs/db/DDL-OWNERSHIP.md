# Decisiones Arquitectónicas de Base de Datos (D2, D7, D8)

## D2 — Base de datos compartida PostgreSQL
- **Decisión:** El backend operativo (Spring Boot) y el panel administrativo (Django) comparten una única base de datos relacional PostgreSQL.
- **Fuente de verdad del modelo:** [`db/schema.sql`](../../db/schema.sql) y [`docs/db/DER.md`](DER.md).

---

## D7 — Propiedad del esquema de base de datos (DDL Ownership)

### Decisión
El esquema PostgreSQL es propiedad exclusiva de `db/schema.sql`. Ningún ORM ejecuta DDL sobre las tablas del dominio.

### Reglas
- **Spring Boot:** `spring.jpa.hibernate.ddl-auto=validate`. No crea ni altera tablas.
- **Django:** `managed=False` en todos los modelos de las 7 tablas compartidas (`rol`, `usuario`, `mesa`, `categoria`, `producto`, `pedido`, `detalle_pedido`). No crea ni altera tablas del dominio.
- **Fuente de verdad:** `db/schema.sql`.

---

## D8 — Algoritmo de hashing de contraseñas (BCrypt vs PBKDF2)

### Contexto
Por defecto, Django almacena contraseñas con `PBKDF2` (`pbkdf2_sha256$<iteraciones>$<salt>$<hash>`), mientras que Spring Security utiliza `BCryptPasswordEncoder` (`$2a$10$...` / `$2b$10$...`). Como ambos sistemas interactúan con la tabla compartida `usuario` (`clave_hash`), usar el formato por defecto de Django rompería el login en Spring Boot.

### Decisión
1. **Estándar en `usuario.clave_hash`:** Todas las contraseñas en la tabla `usuario` se almacenan como hash **BCrypt puro (cost = 10)** con prefijo estándar `$2b$10$...` (o `$2a$10$...`), directamente verificable por `BCryptPasswordEncoder` en Spring Boot y `bcrypt.checkpw()` en Python.
2. **Escritura desde Django (Backoffice):** Al crear o cambiar la contraseña de un usuario operativo desde el panel Django, se genera el hash con la librería `bcrypt` (`bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=10)).decode('utf-8')`) antes de guardarlo en `usuario.clave_hash`. No se utiliza el formato `pbkdf2_sha256$` en esta columna.
3. **Autenticación interna de Django (`auth_user`):** Las tablas internas de administración de Django (`auth_user`) son independientes de la tabla `usuario` del dominio y pueden conservar el hasher por defecto de Django (`PBKDF2`) sin afectar a Spring Boot.

---

## Firmado
- Max Muñoz (Backend Lead)
- Jerardo Cutipa (Backoffice Lead)

