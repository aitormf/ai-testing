# Revisión: spec de Runner de Claude Code y ejecución de tareas (`run`)

<!-- Escrita por review-spec. Es una recomendación: la aprobación la hace una persona cambiando status. -->

## Recomendación
**Devolver.** Hay dos bloqueantes, los dos de seguridad:

- RF-17 promete una lista fija de permisos sin acceso web, pero RF-20 carga los ajustes del usuario y del proyecto, y esos ajustes pueden ampliar esa lista.
- El log sin filtrar choca con la invariante de §6, con SECURITY.md y con AGENTS.md, y la spec no toma una decisión explícita al respecto.

El resto de la spec está bien acotada, y la introducción de los Protocols ya estaba prevista en los ADRs.

## Hallazgos

### Bloqueantes

1. **RF-17 frente a RF-20 (y Seguridad, "Tests negativos"): la lista "fija" de permisos no es fija.**
   - **Qué falla.** RF-20 carga los ajustes de usuario de Claude Code (`~/.claude/settings.json`): reglas `permissions.allow`, servidores MCP y hooks. Como el worktree es una copia del repo evaluado, también carga los ajustes de proyecto de ese repo (`.claude/settings.json`), que son una entrada no fiable. Las reglas `allow` de esas fuentes se suman a las que pasa la CLI, y un servidor MCP puede dar acceso a la red. Por eso no se cumplen tres cosas:
     - "una lista fija y documentada de herramientas permitidas" (RF-17);
     - "sin acceso web" (RF-17);
     - el test negativo "la configuración de permisos con la que se lanza Claude […] no incluye acceso web". Ese test solo comprueba los argumentos de la CLI, no los permisos que tiene de verdad el agente.
   - **Choque con SECURITY.md.** Se juntan acceso a datos privados, contenido no fiable (el repo y el prompt) y comunicación con el exterior (MCP). Es la *lethal trifecta* que SECURITY.md pide evitar.
   - **Arreglo sugerido.** Elegir una de estas dos opciones y reflejarla en RF-17, RF-20, Riesgos y los tests negativos:
     - **(a)** No cargar los ajustes de proyecto del repo evaluado. Para los de usuario, decidir si se cargan con o sin sus reglas de permisos.
     - **(b)** Declarar que los permisos efectivos son la lista fija más los `allow` y los MCP del usuario. En ese caso hay que quitar la garantía "sin acceso web" y documentar el riesgo.

   En los dos casos, el criterio de aceptación tiene que verificar los permisos efectivos, o bien acotar explícitamente lo que se garantiza.

2. **RF-13 y RNF-04 frente a la invariante de §6, SECURITY.md y AGENTS.md: el log sin filtrar puede guardar variables de entorno y credenciales.**
   - **Qué falla.** RF-18 puede pasar `ANTHROPIC_API_KEY` al agente (ver Supuestos). Cualquier comando que el agente ejecute puede volcarla a su salida, por ejemplo un script de test (ver hallazgo 5). RF-13 guarda esa salida sin filtrar, y la CLI la escribe en disco. Esto choca con:
     - la invariante de §6 "Los resultados en disco no contienen variables de entorno";
     - la invariante de §6 "La CLI no lee, guarda ni registra credenciales";
     - SECURITY.md ("Resultados");
     - AGENTS.md ("Nunca leas ni guardes […] variables de entorno en los resultados" y, en Code review, "Marcar siempre: variables de entorno o credenciales en resultados o logs").

     Además, el entorno mínimo cambia otra invariante: "las heredan del entorno". Ahora la CLI elige qué variables pasa, así que tiene que leerlas.

     La spec trata todo esto como un riesgo ("precisar la invariante", solo en ARCHITECTURE.md). No hay un requisito ni una decisión humana explícita, y no menciona ni SECURITY.md ni AGENTS.md.
   - **Arreglo sugerido.** Convertirlo en requisitos verificables:
     - redactar en el log los valores de las variables que la CLI pasa al agente, cosa que la CLI puede hacer porque conoce esos valores;
     - fijar los permisos del log y de `results.json` (por ejemplo, `0600`);
     - que la persona decida explícitamente qué queda fuera de la garantía.

     Después, añadir al Alcance la actualización de §6, SECURITY.md y AGENTS.md en la misma PR, con un criterio de aceptación del tipo "dado un valor de `ANTHROPIC_API_KEY` que el agente imprime, no aparece en `logs/<id>.jsonl`".

### Importantes

3. **Dependencias y RNF-01: el contrato de los Protocols nuevos no está definido, y eso pone en riesgo P5.**
   - **Qué falla.** La spec presenta `Runner`, `Workspace`, `ResultStore` y `RunResult` y aplaza la confirmación al plan, pero no dice qué hace cada parte. Faltan, entre otras cosas:
     - quién aplica el timeout (RF-09);
     - quién atiende la interrupción (RF-22);
     - quién decide dónde va el log;
     - cómo se representan el coste y los tokens;
     - cómo se distingue un runner "no implementado" (RF-08). Hoy `registry.py` solo tiene nombres.

     Si el contrato se queda corto, añadir `codex` obligará a cambiar `domain`, lo que incumple P5 y la regla de AGENTS.md "preguntar antes de cambiar un Protocol". Introducir estos Protocols no choca con ningún ADR (ADR-0001 y ADR-0005 los prevén).
   - **Arreglo sugerido.**
     - Añadir a "Entidades" las responsabilidades mínimas de cada Protocol: qué recibe y devuelve el `Runner`, y que el `Runner` termina su proceso ante el timeout o la interrupción (P3).
     - Indicar que el estado "no implementado" se resuelve en el registro, dentro de `adapters`.
     - Pedir la confirmación humana de los Protocols al aprobar la spec, no en el plan.

4. **RF-17, Riesgos y Preguntas abiertas: `git` como comando permitido escapa del worktree.**
   - **Qué falla.** Un worktree comparte con el repo de la persona el `.git` común: `config`, `hooks` y `refs`. Con `git` permitido por prefijo, el agente puede:
     - cambiar `git config` (por ejemplo, `core.hooksPath`) y dejar código que se ejecutará cuando la persona haga commit en su repo;
     - hacer `git push` o `git remote add`, que es un canal de salida aunque no haya acceso web;
     - borrar ramas o worktrees, o usar `git -C <repo>`.

     Además, la spec no dice si el worktree se crea con HEAD separado o en una rama. Eso decide si "El agente hace commits, crea ramas…" (Casos límite) ensucia las ramas del repo de la persona, y cómo se inspecciona el resultado (user story 2).
   - **Arreglo sugerido.**
     - Concretar ya en la spec el criterio para `git`: subcomandos de solo lectura y los de commit local, y denegar `config`, `push`, `remote`, `worktree` y `-C`.
     - Fijar si el worktree va en HEAD separado o en una rama con nombre (por ejemplo, `ia-testing/<run-id>/<id>`).

5. **RF-17, RF-18 y user story 4: la garantía "no lea mis secretos" no se cumple, y las listas no son verificables.**
   - **Qué falla.** Permitir comandos de "build/test genéricos" (Preguntas abiertas) equivale a dejar ejecutar código arbitrario: el agente edita el script de test y lo lanza, y así se salta todas las reglas `deny`. Además, por defecto Claude Code puede leer fuera del directorio de trabajo. Con `HOME` en el entorno, `~/.claude/.credentials.json` queda al alcance, y no está en la lista de denegación (que acaba en "…").

     Las tres listas de RF-17 y RF-18 (herramientas y comandos permitidos, rutas denegadas y variables de entorno) se describen como "fijas y documentadas", pero no se enumeran. Así, los criterios de aceptación no se pueden verificar.
   - **Arreglo sugerido.**
     - Enumerar las rutas denegadas, incluidas las credenciales de `~/.claude`, y las variables de entorno permitidas.
     - Si la lista de `Bash` se deja para el plan, fijar ahora el criterio con el que se elegirá.
     - Rebajar la user story 4 ("sin supervisión") a lo que de verdad se garantiza, o dejar claro en ella que sigue habiendo riesgo hasta que exista el sandbox.

6. **RF-05 y Supuestos: la ruta de salida en el directorio padre.**
   - **Qué falla.**
     - (a) **Contaminación de la comparación.** Todos los worktrees y los logs de una ejecución son hermanos. Como el agente puede leer fuera de su directorio, la configuración N puede leer el worktree y el log de las anteriores.
     - (b) **No hay alternativa** si el padre no admite escritura: un repo en `/`, un volumen montado o un CI. La spec responde con código 2, pero no ofrece opción para elegir otro directorio.
     - (c) **Ambigüedad en `<nombre-del-repo>`.** No está claro qué pasa si `--repo` apunta a un subdirectorio del repo: ¿se usa la raíz (`git rev-parse --show-toplevel`)? Tampoco está cubierto que el padre sea a su vez un repo git, en cuyo caso aparecería como cambio sin seguimiento.
   - **Arreglo sugerido.**
     - Para (a): añadir una regla `deny` sobre `<run-dir>/logs` y sobre los worktrees hermanos, o asumirlo explícitamente como riesgo.
     - Para (b): valorar una opción `--output-dir`, o declarar que no habrá ninguna.
     - Para (c): fijar que se usa la raíz del repositorio.

7. **RF-09 y RF-22: terminar el proceso del agente.**
   - **Qué falla.** Claude Code lanza procesos hijos: comandos de `Bash` y servidores MCP. Si solo se termina el proceso principal, quedan procesos huérfanos que siguen escribiendo en el worktree después del "timeout" o del "interrupted".
   - **Arreglo sugerido.** Exigir que se termine el grupo de procesos completo y añadirlo a los criterios de aceptación del timeout y del Ctrl-C.

8. **RF-15 y Casos límite frente a ARCHITECTURE.md §9: falla la creación de un worktree a mitad de la ejecución.**
   - **Qué falla.** Los worktrees se crean por configuración: RF-08 dice que los runners no implementados no tienen worktree. La spec no dice qué ocurre si falla `git worktree add` en la segunda configuración, por ejemplo por disco lleno. Puede ser un resultado fallido con código 1 o un error con código 2. Además, §9 dice "error claro antes de lanzar ningún runner", y eso no encaja con crearlos de uno en uno.
   - **Arreglo sugerido.** Definirlo (lo coherente con RF-10 sería un resultado fallido y seguir) y actualizar §9.

9. **Criterios de aceptación: hay requisitos sin criterio.**
   - **Qué falla.** No tienen criterio de aceptación:
     - RF-02 (repositorio y `HEAD` por defecto; `--repo` y `--ref`);
     - RF-05 (sufijo `-2` del `run-id`);
     - RF-09 (timeout de 30 minutos por defecto; `--timeout`);
     - RF-10 (herramienta no autenticada o que termina con error);
     - RF-13 (contenido del log);
     - RF-14 (formato del resumen);
     - RF-17 (denegación en la práctica, más allá del test negativo de configuración);
     - RF-19 (`type` sin efecto).
   - **Arreglo sugerido.** Añadir un "Dado/cuando/entonces" para cada uno.

### Menores

10. **RF-13: formato del log.** El log mezcla la salida de error, que no es JSON, con la salida estructurada en un fichero `.jsonl`. Así, el fichero deja de ser JSONL válido. Arreglo: separar la salida de error en `logs/<id>.stderr.log`, o envolver cada línea en un objeto JSON.
11. **RF-09: `--timeout` sin unidad ni validación.** Falta definir la unidad y qué pasa con valores como `0`, negativos o no numéricos. Lo esperable es un error de argumentos.
12. **RF-11, RF-12 y RF-14: esquema de `results.json` poco preciso.**
    - Faltan las unidades de la duración y la moneda del coste.
    - No dice qué tokens se guardan: entrada, salida o caché.
    - No hay versión del esquema.
    - No dice si el resumen y los avisos van a la salida estándar o a la de error.
    - No dice si `results.json` se escribe solo al final. Si la CLI muere sin pasar por RF-22 (por ejemplo, con `SIGKILL`), no queda constancia de nada.
13. **RF-05: formato del `run-id`.** Falta fijar el formato, si se ordena alfabéticamente y la zona horaria. Además, para que el sufijo `-2` no tenga condiciones de carrera, el directorio tiene que crearse de forma exclusiva.
14. **RF-04 y Casos límite: casos sin cubrir.**
    - ¿Los ficheros sin seguimiento cuentan como "cambios sin commitear"?
    - ¿Tiene sentido avisar cuando `--ref` no es `HEAD`?
    - Faltan los submódulos y Git LFS, que `git worktree add` no inicializa.
15. **Caso límite "el estado depende solo del código de salida".** En modo no interactivo, Claude Code puede terminar con código 0 y aun así marcar `is_error` o agotar los turnos. Arreglo: aclarar el criterio y que `succeeded` no significa "tarea resuelta".
16. **CA "Claude Code no está instalado".** No queda claro si se crean igualmente los worktrees de esas configuraciones.
17. **Riesgos ("ARCHITECTURE.md desalineado"): la lista de documentos a actualizar está incompleta.** Además de §1, §6 y §9, hay que actualizar:
    - §3: cita `karajan.py`;
    - §7: el flujo construye una `Comparison`, y esta spec no lo hace;
    - §10: dice que el fichero de tarea es "dato de entrada del comando `validate`";
    - `docs/config_file.md`, que solo habla de `validate`;
    - SECURITY.md (ver hallazgo 2).

    Arreglo: pasar estas actualizaciones al Alcance.
18. **RF-15 y RF-16: códigos de salida distintos para el mismo error.** Un fichero inválido da código 1 con `validate` y código 2 con `run`. Es coherente, pero conviene decir explícitamente que la diferencia es intencionada, para que el plan no "lo corrija".

## Principios y ADRs
- **P1, P2 y P3:** no hay choque si los Protocols nuevos son Python puro y el timeout y la interrupción viven en `adapters` (hallazgo 3).
- **P4:** sin choque. El plan debe mantener en `app` la orquestación de RF-03 a RF-22, y en `adapters/report` el resumen y los códigos de salida, como ya pasa con `validate`.
- **P5:** en riesgo mientras el contrato del `Runner` no esté definido (hallazgo 3).
- **P6:** el criterio de aceptación de `SECRET_X` tiene que poder probarse sin parchear `subprocess`. Para eso, la construcción del entorno y de los argumentos debe poder testearse sin lanzar Claude, o bien ir en un test `integration`.
- **P8:** la spec no dice si añade dependencias. Conviene decir explícitamente "sin dependencias nuevas".
- **ADR-0001:** coherente. Los Protocols que se introducen están previstos en él, así que no hace falta un ADR nuevo, pero sí la confirmación humana que pide AGENTS.md.
- **ADR-0005:** coherente (un worktree por ejecución, desde el mismo commit, que se conserva). El ADR no fija dónde va el worktree, así que el directorio padre no choca con él. Su mitigación (el comando de limpieza) queda fuera de alcance, y el riesgo ya está declarado.
- **Invariantes de §6 y SECURITY.md:** hay choque (hallazgo 2).

## Preguntas
- ¿Deben cargarse los ajustes de proyecto (`.claude/`) del repositorio evaluado, o solo los del usuario?
- ¿Se acepta pasar `ANTHROPIC_API_KEY` al agente, o solo se admite la sesión de suscripción?
- ¿El worktree va en HEAD separado o en una rama con nombre?
- ¿Se quiere una opción `--output-dir`?

## Riesgos
- Sin sandbox, cualquier comando de build o test permitido convierte las reglas `deny` en una defensa parcial. Hay que documentarlo de forma visible en el README y en SECURITY.md, no solo en la spec.
- Que el agente modifique el `.git` común (`config`, `hooks`) es un daño que dura más allá de la ejecución y afecta al repositorio de la persona, no solo al worktree.
