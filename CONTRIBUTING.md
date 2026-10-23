# Guía de Contribución — restaurante-admin-django

Proyecto: Sistema Integral de Comandas y Gestión para Cevichería "La Casa Blanca"
Equipo: "Error 404" — Ciclo 4, 2026

## 1. Estructura de ramas (GitFlow)

| Rama | Uso |
|---|---|
| `main` | Solo código de entregas finales (releases oficiales). Nadie sube directo aquí. |
| `develop` | Rama de integración donde se une el trabajo semanal de todo el equipo. Nadie sube directo aquí. |
| `feature/PE-xx-nombre` | Rama individual creada por cada integrante para su tarea de Jira. Se elimina tras el merge a develop. |
| `bugfix/PE-xx` | Rama para corrección de errores detectados durante el sprint. |

## 2. Reglas de protección de ramas (GitHub → Settings → Branches)

- **PR obligatorio** antes de mergear en `main` y `develop`.
- **Mínimo 1 aprobación** ("Require approvals": 1) antes del merge.
- **Status checks** obligatorios cuando el pipeline de CI (PE-21) esté disponible.
- **Push directo y force-push bloqueados** en `main` y `develop` para todos los colaboradores, incluidos administradores.

## 3. Convención de nombres de ramas

```
feature/PE-11-login-mapa-mesas
feature/PE-13-catalogo-platos-carrito
bugfix/PE-19-fix-total-carrito
```

El número (PE-xx) debe corresponder siempre al ticket de Jira relacionado, para poder rastrear cada cambio hasta su historia de usuario.

## 4. Estándar de Conventional Commits

Formato: `tipo(PE-xx): descripción breve en minúsculas, en modo imperativo`

| Tipo | Uso | Ejemplo |
|---|---|---|
| `feat` | Nueva funcionalidad | `feat(PE-11): agregar pantalla de login` |
| `fix` | Corrección de error | `fix(PE-11): corregir color de mesas ocupadas` |
| `test` | Pruebas nuevas o modificadas | `test(PE-19): agregar test de LoginViewModel` |
| `docs` | Documentación / manuales | `docs(PE-7): agregar guía de branching` |
| `refactor` | Cambio de código sin alterar funcionalidad | `refactor(PE-13): simplificar adapter de carrito` |

## 5. Flujo de Pull Request

1. Crear la rama `feature/PE-xx-nombre` desde `develop` actualizado.
2. Trabajar y confirmar (commit) siguiendo Conventional Commits.
3. Hacer push de la rama al repositorio remoto.
4. Abrir un Pull Request hacia `develop`, describiendo qué se hizo y enlazando el ticket de Jira.
5. Esperar la revisión ("Approve") de al menos 1 compañero del equipo.
6. Resolver comentarios si los hay, y recién ahí hacer el merge (preferir "Squash and merge" para mantener el historial limpio).
7. Eliminar la rama `feature` tras el merge y actualizar el ticket de Jira a "Listo / Done".

## 6. Resolución de conflictos de merge

Ante un conflicto detectado por GitHub en el Pull Request:

1. Actualizar la rama local: `git checkout develop && git pull`
2. Volver a la rama feature y traer los cambios: `git checkout feature/PE-xx-nombre && git merge develop`
3. Resolver manualmente los archivos marcados con conflicto (`<<<<<<<` / `=======` / `>>>>>>>`).
4. Confirmar la resolución: `git add . && git commit`
5. Volver a subir la rama (`git push`) y el Pull Request se actualiza automáticamente.
