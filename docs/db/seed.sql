-- Población inicial de datos para pruebas locales
-- NOTA DE SEGURIDAD: Todos los usuarios tienen la contraseña "password123".
-- Hash BCrypt real generado con factor de costo 10: $2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa

-- 1. Roles
INSERT INTO rol (nombre) VALUES 
('Administrador'), ('Mozo'), ('Cocinero'), ('Cajero');

-- 2. Usuarios de Prueba (Datos ficticios, sin información personal real)
INSERT INTO usuario (username, password_hash, rol_id) VALUES 
('admin_test', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 1),
('mozo_01', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 2),
('mozo_02', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 2),
('cocinero_01', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 3),
('cajero_01', '$2a$10$vI8aWBnW3fID.ZQ4/zo1G.q1lRps.9cGLcZEiGDMVr5yUP1KUOYTa', 4);

-- 3. Categorías (Alineado con especificaciones PE-2 y API)
INSERT INTO categoria (nombre) VALUES 
('Ceviches & Fríos'), ('Calientes & Frituras'), ('Bebidas'), ('Postres');

-- 4. Productos de Ejemplo
INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id) VALUES 
('Ceviche Clásico', 'Pescado fresco del día con limón, ají limo y cebolla.', 48.00, true, 1),
('Leche de Tigre', 'Concentrado de ceviche con trozos de pescado y mariscos.', 25.00, true, 1),
('Jalea Mixta', 'Fritura de pescados y mariscos con yuca y sarsa criolla.', 55.00, true, 2),
('Chicha Morada', 'Jarra de 1 litro de chicha morada tradicional.', 15.00, true, 3),
('Suspiro a la Limeña', 'Clásico postre peruano a base de manjar blanco.', 12.00, true, 4);

-- 5. Mesas (15 mesas distribuidas según PE-1: 7 en primer piso, 6+2 en segundo piso)
INSERT INTO mesa (numero, capacidad, ubicacion, estado) VALUES 
(1, 4, 'Primer Piso', 'LIBRE'), (2, 4, 'Primer Piso', 'LIBRE'),
(3, 4, 'Primer Piso', 'LIBRE'), (4, 6, 'Primer Piso', 'LIBRE'),
(5, 6, 'Primer Piso', 'LIBRE'), (6, 2, 'Primer Piso', 'LIBRE'),
(7, 2, 'Primer Piso', 'LIBRE'),
(8, 4, 'Segundo Piso', 'LIBRE'), (9, 4, 'Segundo Piso', 'LIBRE'),
(10, 4, 'Segundo Piso', 'LIBRE'), (11, 6, 'Segundo Piso', 'LIBRE'),
(12, 6, 'Segundo Piso', 'LIBRE'), (13, 2, 'Segundo Piso', 'LIBRE'),
(14, 2, 'Segundo Piso', 'LIBRE'), (15, 8, 'Segundo Piso - Privado', 'LIBRE');