# D8 — Hashing de Contraseñas en Tabla Compartida `usuario` (BCrypt vs PBKDF2)

## Contexto
El sistema cuenta con dos aplicaciones que acceden a la misma base de datos PostgreSQL:
- **Backend Operativo (Spring Boot):** Autentica a los usuarios operativos (`ADMIN`, `MOZO`, `COCINERO`, `CAJERO`) leyendo la columna `usuario.clave_hash` mediante `BCryptPasswordEncoder`.
- **Panel Administrativo (Django):** Gestiona el CRUD de usuarios operativos en la tabla `usuario`. Por defecto, Django utiliza `PBKDF2PasswordHasher` (`pbkdf2_sha256$...`), el cual es incompatible con `BCryptPasswordEncoder` de Spring Security.

## Decisión
1. **Formato único en `usuario.clave_hash`:** Se adopta **BCrypt (cost factor 10)** con formato estándar `$2b$10$...` / `$2a$10$...` como único algoritmo válido para la columna `clave_hash` de la tabla `usuario`.
2. **Generación de hashes desde Django:** Cuando el panel administrativo de Django cree o actualice un registro en `usuario`, generará el valor de `clave_hash` utilizando la librería `bcrypt` de Python:
   ```python
   import bcrypt

   clave_hash = bcrypt.hashpw(
       raw_password.encode("utf-8"),
       bcrypt.gensalt(rounds=10),
   ).decode("utf-8")
   ```
3. **Semilla (`db/seed.sql`):** Todos los usuarios de prueba en `db/seed.sql` utilizan el hash BCrypt real (cost 10) correspondiente a `"password123"`:
   ```text
   $2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S
   ```
4. **Separación de `auth_user`:** Las tablas internas de sesión/administración propias de Django (`auth_user`) no colisionan con la tabla `usuario` del negocio (`managed = False`) y pueden mantener `PBKDF2` para el superusuario del framework si fuera necesario.

## Firmado
- Max Muñoz (Backend Lead)
- Jerardo Cutipa (Backoffice Lead)

