# ia-testing

**ia-testing** es una CLI local para comparar cómo resuelven tareas de programación distintos agentes de IA. Lanza la misma tarea contra varios *runners* y recoge los resultados para poder compararlos. La primera versión usa [Karajan Code](https://karajancode.com), y el diseño permite añadir más tareas y llamar directamente a las CLIs de los agentes (Claude Code, Codex, Gemini CLI…).

**Queda fuera:** no es un servicio ni tiene interfaz web; todo se ejecuta en la máquina de quien la usa. No instala ni gestiona las herramientas externas ni sus credenciales, sino que da por hecho que ya están en el sistema.

## Documentación

- [Arquitectura y principios](docs/ARCHITECTURE.md)
- [Decisiones (ADRs)](docs/adr/README.md)
- [Cómo contribuir](CONTRIBUTING.md)
- [Seguridad](SECURITY.md)
- [Instrucciones para agentes de IA](AGENTS.md)
