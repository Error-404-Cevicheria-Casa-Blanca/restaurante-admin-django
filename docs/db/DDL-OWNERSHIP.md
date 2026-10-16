# D7 — Propiedad del esquema de base de datos

## Decisión
El esquema PostgreSQL es propiedad de db/schema.sql.

## Reglas
- Spring Boot: spring.jpa.hibernate.ddl-auto=validate. No crea tablas.
- Django: managed=False en modelos de tablas compartidas. No crea tablas.
- Fuente de verdad: db/schema.sql.

## Firmado
- Max Muñoz (Backend Lead)
- Jerardo Cutipa (Backoffice Lead)
