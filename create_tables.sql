-- ============================================
-- Script para crear tablas del sistema de
-- Control de Asistencia GM
-- ============================================

-- Tabla de roles (admin, maestro, alumno, etc.)
CREATE TABLE IF NOT EXISTS roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion VARCHAR(200),
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insertar roles base
INSERT IGNORE INTO roles (nombre, descripcion) VALUES
    ('admin', 'Administrador del sistema'),
    ('maestro', 'Docente que registra asistencias'),
    ('alumno', 'Estudiante del plantel');

-- Tabla de usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol_id INT NOT NULL DEFAULT 3,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (rol_id) REFERENCES roles(id)
);

-- Índice para búsqueda rápida por email (login)
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email);
