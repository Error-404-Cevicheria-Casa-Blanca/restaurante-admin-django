-- Población inicial de datos
-- NOTA DE SEGURIDAD: Todos los usuarios tienen la contraseña "password123"
-- Hash BCrypt real (cost 10) generado con bcrypt.hashpw para "password123":
-- $2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S

-- 1. Roles (ADMIN en lugar de ADMINISTRADOR)
INSERT INTO rol (nombre) VALUES 
('ADMIN'), ('MOZO'), ('COCINERO'), ('CAJERO');

-- 2. Usuarios (Cambiado de password_hash a clave_hash)
INSERT INTO usuario (username, clave_hash, rol_id) VALUES 
('admin_test', '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S', 1),
('mozo_01', '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S', 2),
('mozo_02', '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S', 2),
('cocinero_01', '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S', 3),
('cajero_01', '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S', 4);

-- 3. Categorías (Según PE-8 / API-v1.md)
INSERT INTO categoria (nombre) VALUES 
('Entradas'), ('Platos de Fondo'), ('Bebidas'), ('Postres');

-- 4. Productos de Ejemplo
INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url) VALUES 
('Ceviche Clásico', 'Pescado fresco del día con limón.', 48.00, true, 1, NULL),
('Leche de Tigre', 'Concentrado de ceviche.', 25.00, true, 1, NULL),
('Jalea Mixta', 'Fritura de pescados y mariscos.', 55.00, true, 2, NULL),
('Chicha Morada', 'Jarra de 1 litro de chicha.', 15.00, true, 3, NULL),
('Suspiro a la Limeña', 'Clásico postre peruano.', 12.00, true, 4, NULL);

-- 5. Mesas (13 mesas exactas según PE-1, con "piso" en minúscula)
INSERT INTO mesa (numero, capacidad, ubicacion, estado) VALUES 
(1, 4, 'Primer piso', 'LIBRE'), (2, 4, 'Primer piso', 'LIBRE'),
(3, 4, 'Primer piso', 'LIBRE'), (4, 6, 'Primer piso', 'LIBRE'),
(5, 6, 'Primer piso', 'LIBRE'), (6, 2, 'Primer piso', 'LIBRE'),
(7, 2, 'Primer piso', 'LIBRE'),
(8, 4, 'Segundo piso', 'LIBRE'), (9, 4, 'Segundo piso', 'LIBRE'),
(10, 4, 'Segundo piso', 'LIBRE'), (11, 6, 'Segundo piso', 'LIBRE'),
(12, 6, 'Segundo piso', 'LIBRE'), (13, 2, 'Segundo piso', 'LIBRE');