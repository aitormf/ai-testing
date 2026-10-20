# Revisión: plan de Fichero de configuración de la tarea

<!-- Escrita por review-spec. Es una recomendación: la aprobación la hace una persona cambiando status. -->

## Recomendación
**Listo para aprobar**, aunque conviene aplicar antes los hallazgos importantes. No hay
bloqueantes: todos los criterios de aceptación (CA-01 a CA-18) y todos los tests negativos de
Seguridad tienen un test, y el plan no choca con ningún principio ni ADR. Aun así, hay cinco
puntos importantes que dejan huecos frente a RNF-05 y RF-09 y frente a la definición de
"falla" de la spec. También queda abierta la forma exacta de usar cyclopts v4.

## Hallazgos

### Bloqueantes

Ninguno.

### Importantes

1. **Componentes (`adapters/task_file.py`): un `OSError` no previsto saldría con traza (RNF-05).**
   - Qué falla: el adapter solo convierte `FileNotFoundError`, `IsADirectoryError` y
     `PermissionError`. Otros errores de lectura habituales se propagarían hasta cyclopts y
     mostrarían una traza de Python. Por ejemplo:
     - `NotADirectoryError`: `ia-testing validate fichero.toml/otro.toml`;
     - `OSError` con `ENAMETOOLONG`, `ELOOP` (bucle de enlaces simbólicos) o `EIO`.
   - Arreglo sugerido: después de los casos concretos, capturar `OSError` como último recurso
     con un motivo genérico (p. ej. `cannot read file`), sin interpolar `strerror` ni la
     excepción. Añadirlo a la tabla de motivos y crear un test, p. ej. con `NotADirectoryError`,
     que se reproduce en `tmp_path` sin parchear nada.
   - **Decisión:** Aplicado. `OSError` como último recurso con `cannot read file`, sin interpolar `strerror`; test `test_not_a_directory`.

2. **Riesgos y Contratos (TOML mal formado): `str(exc)` puede repetir contenido del fichero (RF-09, Seguridad).**
   - Qué falla: el plan escribe `invalid TOML: <mensaje de tomllib>` y confía en que
     `test_malformed_toml_does_not_echo_content` detecte cualquier eco. Un solo test con una
     entrada concreta no cubre todos los mensajes. En 3.13, algunos mensajes de `tomllib`
     incluyen trozos del documento:
     - nombres de clave: `Cannot declare ('runners',) twice`, `Cannot overwrite a value`,
       `Cannot redefine namespace …`;
     - el carácter no permitido: `Illegal character '\x00'`.

     Hoy no hay ninguno que repita el valor completo de un campo. Pero eso depende de detalles
     internos de la stdlib que pueden cambiar.
   - Arreglo sugerido: no reenviar el texto del parser. Sacar solo `line N, column M` con una
     expresión regular sobre `str(exc)` (en 3.13 no existen `lineno`/`colno`, como dice
     bien el plan) y escribir `invalid TOML at line N, column M`. Si no casa, escribir
     `invalid TOML`. Con eso se cumplen CA-15 y RF-09 sin depender del texto de `tomllib`.
     El test de CA-15 debería comprobar el número de línea concreto (p. ej. `line 3`), no
     solo la palabra `line`.
   - **Decisión:** Aplicado. Mensaje `invalid TOML at line N, column M` (o `invalid TOML`) extraído con regex; no se reenvía el texto del parser. CA-15 comprueba la línea concreta.

3. **Pruebas: la definición de "falla" no se comprueba de extremo a extremo con los errores de fichero (CA-13, CA-15, CA-16, RNF-05).**
   - Qué falla: la spec define "falla" como código 1, stdout vacío, `<path>: <reason>` en
     stderr y sin traza. CA-13, CA-15 y CA-16 solo se prueban en el adapter, que lanza
     `InvalidTaskFile`. Ningún test recorre `app` → `report` → código de salida con un fichero
     que no existe, binario o mal formado. Además, la fila RNF-05 dice que "los tests del
     adapter comprueban que stderr no contiene `Traceback`", pero los tests del adapter no
     escriben en stderr, así que esa comprobación no tiene sentido ahí. Tampoco hay ningún
     test de `app.validate_task_file` aparte de los de la CLI y la documentación.
   - Arreglo sugerido: añadir un test de CLI parametrizado (fichero inexistente, directorio,
     binario, TOML mal formado) que compruebe el código 1, stdout vacío, que stderr empieza
     por la ruta y que no contiene `Traceback`. Corregir la fila RNF-05 para que dependa de
     los tests de CLI. Si se quiere un test de `app`, usar el `TomlTaskFileSource` real con
     `tmp_path`: AGENTS.md solo permite como doble el runner falso.
   - **Decisión:** Aplicado. Test de CLI parametrizado para errores de fichero; fila RNF-05 corregida; test de `app` con el source real en `tmp_path`.

4. **Riesgos ("Códigos de salida de cyclopts") y Pruebas: el comportamiento de cyclopts v4 queda sin decidir.**
   - Qué falla: el plan fija `cyclopts>=4,<5` pero dice "según la versión… `sys.exit(cli_app())`
     si hace falta". Según la documentación de cyclopts v4, `App.__call__` usa por defecto
     `result_action="print_non_int_sys_exit"`: cuando el comando devuelve un `int`, llama a
     `sys.exit(int)`, también con 0. Eso tiene dos consecuencias:
     - los tests que llaman a `cli_app(["validate", …])` "con `capsys`" recibirán un
       `SystemExit` incluso en CA-01;
     - el `sys.exit(cli_app())` de `main()` sobra o es ambiguo.
   - Arreglo sugerido: elegir una opción y escribirla en el plan.
     - (a) Dejar el valor por defecto. Los tests de CLI usan
       `pytest.raises(SystemExit)` y comprueban `excinfo.value.code`, y `main()` solo llama
       a `cli_app()`.
     - (b) Crear `App(result_action="return_value")`. Los tests comprueban el `int`
       devuelto, y `main()` hace `sys.exit(cli_app())`.

     En las dos opciones, `cli.py` debe pasar `sys.stdout`/`sys.stderr` a `print_validation`
     al llamarla, no como valor por defecto ligado al importar, para que `capsys` los capture.
     Hay que confirmarlo con la versión que resuelva `uv add`.
   - **Decisión:** Aplicado, opción (b): `App(result_action="return_value")`, `main()` hace `sys.exit(cli_app())`, `sys.stdout`/`sys.stderr` se pasan al llamar.

5. **Riesgos ("Tamaño de la PR 2") y reparto en PRs: la PR 3 de reserva contradice RNF-06, RNF-04 y ARCHITECTURE §12.**
   - Qué falla:
     - si `docs/` pasa a una PR 3, `test_docs.py` (CA-18) se queda en la PR 2 sin el
       Markdown que valida, o la PR 2 se integra sin cumplir RNF-04;
     - RNF-06 y ARCHITECTURE §12 piden actualizar `ARCHITECTURE.md` en la misma PR que
       cambia la estructura. Sin embargo, la PR 1 ya añade un Protocol a `domain`
       (`TaskFileSource`, que cambia la fila de §3) y el registro en `adapters/runners/`,
       mientras que el plan deja §3 para la PR 2.
   - Arreglo sugerido: actualizar §3 (Protocols de `domain` y registro) en la PR 1, junto
     con lo que la introduce. Si la PR 2 se pasa de tamaño, partirla por código, no
     separando código y documentación. Por ejemplo, PR 2 con adapter y `app`, y PR 3 con la
     CLI, `docs/config_file.md`, `test_docs.py` y §8/§10. Indicar también qué tests van en
     cada PR (la tabla de Pruebas no tiene columna de PR).
   - **Decisión:** Modificado. Se mantienen 2 PRs aunque superen las 400 líneas (excepción aceptada por @aitormf al sentar las bases del proyecto); se elimina la PR 3 de reserva. ARCHITECTURE §3 se actualiza en la PR 1 para lo que introduce (Protocol `TaskFileSource`, registro de runners); el resto (§3 del adapter y `report`, §8, §10) en la PR 2.

### Menores

6. **Arquitectura propuesta: `adapters/task_file.py` no "encaja en las carpetas previstas en §3".**
   §3 solo prevé `runners/`, `workspace/`, `storage/` y `report/`, y el fichero va suelto en
   la raíz de `adapters/`. Arreglo: corregir la frase y añadir una fila en el mapa de §3 para
   el adapter de lectura del fichero de tarea (o ponerlo en una subcarpeta).
   - **Decisión:** Aplicado. Se corrige la frase y se añade al mapa de ARCHITECTURE §3 una fila para `adapters/task_file.py` (PR 2).

7. **Reglas de validación: elementos de `runners` que no son tablas.** El plan cubre `runners`
   como tabla y `runners = []`, pero no `runners = [1]` ni `runners = ["a"]`. Sin una regla,
   el código puede tratar el elemento como `Mapping` y fallar con traza. Arreglo: un motivo
   (p. ej. `runners[0]: expected a table`) y añadirlo a `test_wrong_types`.
   - **Decisión:** Aplazado por decisión de @aitormf: queda abierto para la implementación.

8. **Reglas de validación (prompt efectivo): caso del prompt común en blanco.** No queda claro
   si un `prompt` común con solo espacios da un error en `prompt` y, además, uno en
   `runners[i].prompt` por cada configuración sin prompt propio, o solo el primero. Arreglo:
   decirlo de forma explícita y cubrirlo en `test_blank_text_fields_are_errors`.
   - **Decisión:** Modificado. Un prompt común en blanco da un único error `prompt: must not be empty`, como los demás campos vacíos, sin `missing prompt` en cada runner.

9. **Contratos: orden de los runners permitidos en el mensaje.** La tabla escribe un texto fijo
   (`claude, codex, opencode`), pero `runner_names` es un `Collection` inyectado. Si llega un
   `set`, el mensaje no es determinista. Arreglo: construir el mensaje desde `runner_names`
   (lo exige `test_runner_names_are_injected`) en un orden fijo, el del registro o el
   alfabético.
   - **Decisión:** Aplazado por decisión de @aitormf: queda abierto para la implementación.

10. **Pruebas (CA-13): contenido del fichero binario sin fijar.** Unos bytes binarios que son
    UTF-8 válido (p. ej. con `\x00`) dan `invalid TOML`, no `not valid UTF-8`. Arreglo: fijar
    los bytes de cada test, p. ej. `b"\x89PNG\r\n\x1a\n"` para el que no es UTF-8.
    - **Decisión:** Modificado. Fichero binario de 20 KB con bytes fijos (`bytes(range(256)) * 80`), que no es UTF-8 válido → `not valid UTF-8`.

11. **Supuesto no declarado: BOM de UTF-8.** Con `decode("utf-8")`, un fichero guardado con
    BOM da `invalid TOML`. Arreglo: declarar si se acepta (`utf-8-sig`) o si se rechaza, y
    documentarlo en `docs/config_file.md`.
    - **Decisión:** Aplazado por decisión de @aitormf: queda abierto para la implementación.

12. **Pruebas (CA-18): "el primer bloque `toml`" es una convención frágil.** Si la
    documentación añade otro bloque `toml` (p. ej. un ejemplo de error), el test puede validar
    el que no toca. Arreglo: validar todos los bloques `toml` de `docs/config_file.md` o
    marcar el ejemplo completo de forma explícita.
    - **Decisión:** Aplazado por decisión de @aitormf: queda abierto para la implementación.

13. **Dependencias transitivas de cyclopts (P8).** `uv.lock` incluirá las dependencias de
    cyclopts (Rich, ya aceptado en ADR-0004, y otras como `attrs`, `docstring-parser` y
    `rich-rst`). Arreglo: decir en el plan que se aceptan como parte de ADR-0002 y que se
    revisan en el diff de `uv.lock` de la PR.
    - **Decisión:** Descartado por decisión de @aitormf: no se declaran en el plan.

## Principios y ADRs
- **P1:** se cumple. `domain/task_file.py` usa solo la stdlib (`dataclasses`, `enum`, `re`,
  `typing`) y recibe los datos ya parseados.
- **P2:** se cumple. El contrato `layers` de import-linter deja que una capa superior importe
  cualquier capa inferior, así que `cli → adapters.report`, `cli → adapters.runners.registry`,
  `cli → app` y `adapters → domain` (para `InvalidTaskFile` y `FieldError`) están permitidos.
- **P3:** no aplica. No hay `subprocess`, y `tomllib` y la E/S están en `adapters`.
- **P4 / ADR-0002:** se cumple. Escribir `OK` o los errores en `adapters/report/validation.py`
  es coherente con §3 ("Salida por terminal" en `adapters/report/`) y con §7, paso 6 (la CLI
  pasa el resultado al adapter de informe). `cli.py` queda sin `if` ni `try`. Ver el hallazgo
  4 sobre cómo se obtiene el código de salida.
- **P5 / ADR-0001 / §6:** se cumple. Los nombres de runner se inyectan desde un registro
  explícito en `adapters/runners/`, y hay un test con un nombre inventado.
- **P6 / AGENTS.md:** se cumple. No hay dobles aparte de los permitidos: ficheros reales en
  `tmp_path` y ningún parche.
- **P8 / ADR-0002 / ADR-0004:** cyclopts ya está aceptado y fijado a la versión mayor 4.
  @aitormf ha aprobado el cambio en `pyproject.toml`. Ver el hallazgo 13.
- **Protocol nuevo `TaskFileSource`** y sustitución del test del saludo: aprobados por
  @aitormf, según dice el plan.
- **ADR-0005:** no le afecta (RNF-02).

## Preguntas
- Para cyclopts v4, ¿opción (a) o (b) del hallazgo 4?
- ¿Se acepta el BOM de UTF-8 en el fichero de tarea (hallazgo 11)?
- Decisiones abiertas 1 a 4 del plan: son interpretaciones razonables de la spec y no
  contradicen ningún requisito. Las tiene que confirmar la persona que apruebe.

## Riesgos
- §7 (Flujo principal) dice que `cli.py` "parsea la tarea y los runners pedidos". Con el
  fichero de tarea, quien lo lee es un adapter. RNF-06 solo exige actualizar §3, §8 y §10,
  pero la spec de ejecución tendrá que revisar §7.
- `parse_task_file` construye un `TaskFile` que `validate` descarta. Es aceptable porque la
  spec de ejecución lo usará, pero hasta entonces solo lo cubren los tests de `domain`.
