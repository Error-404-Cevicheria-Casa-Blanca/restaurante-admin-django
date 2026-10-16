-- Población inicial de datos
-- NOTA DE SEGURIDAD: Todos los usuarios tienen la contraseña "password123"
-- Hash BCrypt real (cost 10) validado matemáticamente para "password123":
-- $2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa

-- 1. Roles (ADMIN en lugar de ADMINISTRADOR)
INSERT INTO rol (nombre) VALUES 
('ADMIN'), ('MOZO'), ('COCINERO'), ('CAJERO');

-- 2. Usuarios (Cambiado de password_hash a clave_hash)
INSERT INTO usuario (username, clave_hash, rol_id) VALUES 
('admin_test', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 1),
('mozo_01', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 2),
('mozo_02', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 2),
('cocinero_01', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 3),
('cajero_01', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 4);

-- 3. Categorías (Según PE-8 / API-v1.md)
INSERT INTO categoria (nombre) VALUES 
('Entradas'), ('Platos de Fondo'), ('Bebidas'), ('Postres');

-- 4. Productos de Ejemplo
INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id) VALUES 
('Ceviche Clásico', 'Pescado fresco del día con limón.', 48.00, true, 1),
('Leche de Tigre', 'Concentrado de ceviche.', 25.00, true, 1),
('Jalea Mixta', 'Fritura de pescados y mariscos.', 55.00, true, 2),
('Chicha Morada', 'Jarra de 1 litro de chicha.', 15.00, true, 3),
('Suspiro a la Limeña', 'Clásico postre peruano.', 12.00, true, 4);

-- 5. Mesas (13 mesas exactas según PE-1, con "piso" en minúscula)
INSERT INTO mesa (numero, capacidad, ubicacion, estado) VALUES 
(1, 4, 'Primer piso', 'LIBRE'), (2, 4, 'Primer piso', 'LIBRE'),
(3, 4, 'Primer piso', 'LIBRE'), (4, 6, 'Primer piso', 'LIBRE'),
(5, 6, 'Primer piso', 'LIBRE'), (6, 2, 'Primer piso', 'LIBRE'),
(7, 2, 'Primer piso', 'LIBRE'),
(8, 4, 'Segundo piso', 'LIBRE'), (9, 4, 'Segundo piso', 'LIBRE'),
(10, 4, 'Segundo piso', 'LIBRE'), (11, 6, 'Segundo piso', 'LIBRE'),
(12, 6, 'Segundo piso', 'LIBRE'), (13, 2, 'Segundo piso', 'LIBRE');