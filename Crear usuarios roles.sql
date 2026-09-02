USE gmadministracion;

-- Roles del sistema
CREATE TABLE IF NOT EXISTS roles (
    idrol INT AUTO_INCREMENT PRIMARY KEY,
    nombre_rol VARCHAR(50) NOT NULL UNIQUE
);

INSERT INTO roles (nombre_rol)
SELECT * FROM (SELECT 'practicante') AS tmp
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre_rol = 'practicante');

INSERT INTO roles (nombre_rol)
SELECT * FROM (SELECT 'administrador') AS tmp
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre_rol = 'administrador');

-- Usuarios que pueden loguearse (uno por practicante)
CREATE TABLE IF NOT EXISTS usuarios (
    idusuario INT AUTO_INCREMENT PRIMARY KEY,
    idpracticante INT NOT NULL UNIQUE,
    codigo_acceso VARCHAR(30) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    idrol INT NOT NULL,
    activo BOOLEAN DEFAULT TRUE,
    CONSTRAINT fk_usuario_practicante
        FOREIGN KEY (idpracticante) REFERENCES practicantes(idpracticante)
        ON DELETE CASCADE,
    CONSTRAINT fk_usuario_rol
        FOREIGN KEY (idrol) REFERENCES roles(idrol)
);

-- Verificación
SELECT * FROM roles;
DESCRIBE usuarios;