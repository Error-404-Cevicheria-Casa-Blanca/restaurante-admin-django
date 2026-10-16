# Modelo Entidad-Relación (DER) - Cevichería La Casa Blanca

El siguiente diagrama detalla la estructura relacional centralizada que compartirán Django y Java.

## Diagrama (Mermaid)
```mermaid
erDiagram
    ROL {
        int id PK
        string nombre "Administrador, Mozo, Cocinero, Cajero"
    }
    USUARIO {
        int id PK
        string username UK
        string clave_hash
        int rol_id FK
    }
    MESA {
        int id PK
        int numero UK
        int capacidad
        string ubicacion
        string estado "LIBRE, OCUPADA, ATENDIDA, CUENTA_SOLICITADA"
    }
    CATEGORIA {
        int id PK
        string nombre
    }
    PRODUCTO {
        int id PK
        string nombre
        string descripcion
        numeric precio
        boolean disponible
        int categoria_id FK
    }
    PEDIDO {
        int id PK
        int mesa_id FK
        int mozo_id FK
        string estado "Pendiente, Cocinando, Listo, Servido, Cobrado"
        numeric total
        timestamp fecha_creacion
    }
    DETALLE_PEDIDO {
        int id PK
        int pedido_id FK
        int producto_id FK
        int cantidad
        string notas
        numeric subtotal
    }

    ROL ||--o{ USUARIO : "asigna"
    CATEGORIA ||--o{ PRODUCTO : "agrupa"
    MESA ||--o{ PEDIDO : "recibe"
    USUARIO ||--o{ PEDIDO : "registra (Mozo)"
    PEDIDO ||--|{ DETALLE_PEDIDO : "contiene"
    PRODUCTO ||--o{ DETALLE_PEDIDO : "incluye"