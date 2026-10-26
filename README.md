# ia-testing

**ia-testing** es una CLI local para comparar cómo resuelven tareas de programación distintos agentes de IA. Lanza la misma tarea contra varios *runners* y recoge los resultados para poder compararlos. El primer runner implementado es [Claude Code](https://claude.com/claude-code), que se lanza directamente como CLI; el diseño permite añadir más runners (Codex, OpenCode, Karajan Code, Gemini CLI…) y más tareas.

## Uso

```
ia-testing validate <fichero>   # valida un fichero de tarea
ia-testing run <fichero>        # lo ejecuta: un worktree y un agente por configuración
```

`run` crea un `git worktree` y una rama por configuración de runner, todos desde el mismo commit, lanza el agente en cada uno y deja en disco `results.json` y los logs completos. Admite `--repo`, `--ref`, `--timeout` (minutos, 30 por defecto) y `--output-dir`. Detalles, estructura del directorio de salida y esquema de `results.json` en [`docs/run.md`](docs/run.md).

> **Aviso:** `run` lanza Claude Code con `bypassPermissions`: el agente actúa **sin restricciones de permisos** con los permisos de tu usuario, y un worktree no es un sandbox. Lee los [riesgos](docs/run.md#antes-de-usarlo-permisos-y-riesgos) antes de usarlo.

**Queda fuera:** no es un servicio ni tiene interfaz web; todo se ejecuta en la máquina de quien la usa. No instala ni gestiona las herramientas externas ni sus credenciales, sino que da por hecho que ya están en el sistema.

## Documentación

- [Arquitectura y principios](docs/ARCHITECTURE.md)
- [Fichero de tarea (esquema de `validate` y `run`)](docs/config_file.md)
- [Comando `run`: uso, resultados y riesgos](docs/run.md)
- [Decisiones (ADRs)](docs/adr/README.md)
- [Cómo contribuir](CONTRIBUTING.md)
- [Seguridad](SECURITY.md)
- [Instrucciones para agentes de IA](AGENTS.md)

## Licencia

[GPL-3.0-or-later](LICENSE).
