## Planificador de proyectos

Esta aplicación web permite introducir proyectos y planificar automáticamente sus
fases utilizando la disponibilidad de los trabajadores.

### Uso rápido

```bash
pip install flask
python app.py
```

Visita `http://localhost:5000` en tu navegador para ir directamente a la vista
**Completo**, que combina el calendario, los proyectos y el formulario de alta.
El calendario precarga desde tres meses antes hasta seis meses después de la fecha
actual para que puedas desplazarte por todo ese periodo manteniendo pulsada la
tecla **Shift** mientras giras la rueda del ratón. El botón **HOY** centra la
tabla en el día actual. La primera vez que entras en cada vista el calendario se
coloca automáticamente en el día actual y, si recargas la página, recuerda la
posición en la que estabas. Puedes filtrar por nombre de proyecto y cliente desde
los dos cuadros de búsqueda.

Los campos de fecha de los distintos formularios aparecen vacíos por defecto.
Puedes introducir las fechas como `dd-mm` o `dd/mm`; si no incluyes el año,
se tomará automáticamente el año en curso.

Todos los proyectos se guardan por defecto en `data/projects.json`. La
aplicación lee este archivo cada vez que se carga la página principal (la vista
**Completo**), de modo que si añades manualmente proyectos ahí también formarán
parte de la planificación. Si quieres conservar los datos en otra ubicación,
define la variable de entorno `EFIMERO_DATA_DIR` con la ruta a tu carpeta antes
de iniciar la aplicación.

 También puedes añadir **Hitos** indicando una descripción y una fecha. En ambas
 vistas de calendario aparecerá una línea roja en la fecha del hito y la
 descripción se muestra en horizontal dentro de su celda en color rojo. Existe
 una pestaña **Hitos** que muestra la lista completa y permite eliminarlos con
 una **X** roja.

La pestaña **Completo** reúne todas las vistas en una sola página. En la
parte superior se muestran, de izquierda a derecha, el formulario de alta, el
de hitos y la lista de conflictos. Debajo aparecen el calendario y, al final,
la lista de proyectos. Cada sección se expande por
completo y la página ofrece una barra de desplazamiento vertical para consultar
la información cómodamente sin necesidad de reducir el zoom. El
calendario muestra el número de semana una sola vez por semana, en negrita y
color violeta. Puedes desplazarte horizontalmente por el calendario
mientras mantienes pulsada la tecla **Shift** y giras la rueda del ratón
sobre la tabla. Las columnas del calendario son ahora el doble de anchas para
facilitar la lectura y cada tarea se muestra como mucho en dos líneas, con el
exceso recortado.

Los fines de semana se representan con una franja negra que agrupa el sábado y el domingo en lugar de mostrar ambas columnas. Esa franja ocupa solamente una quinta parte del ancho que tenía anteriormente, de modo que queda como una línea muy estrecha.

En la pestaña **Proyectos** puedes ver las horas de cada fase y seleccionar la
persona asignada desde un desplegable. Cualquier cambio se guarda
automáticamente. Junto a cada proyecto hay un botón rojo con una **X** para
eliminarlo. Al borrar un proyecto se vuelve a calcular la planificación y en la
lista de conflictos aparece un aviso indicando la eliminación y los cambios que
ha producido.
Si se modifica la prioridad de un proyecto también se vuelve a programar y en la
lista de conflictos se añade una nota indicando qué otros proyectos han cambiado
de fechas debido a esa prioridad. La nota muestra el nombre y cliente de cada
proyecto afectado junto con un ✔ verde si ahora llega a su límite o una ❌
roja en caso contrario.
Puedes pulsar sobre el nombre de un proyecto en la lista de conflictos para
que el calendario salte hasta sus tareas y las resalte igual que si hubieras
hecho clic en ellas, incluso aunque estén fuera del rango visible.
Junto al título de **Conflictos** en la vista **Completo** hay un botón **Reportar bug**. Al pulsarlo se abre un formulario donde debes indicar quién registra la incidencia, en qué pestaña ocurrió, con qué frecuencia sucede y una descripción detallada del problema. Todos los campos son obligatorios.
Al enviar el formulario se asigna un número de BUG y se remite un correo con un resumen a `irodriguez@caldereria-cpk.es`.

Al crear nuevos proyectos, el planificador asigna cada fase a la persona
que pueda comenzarla antes. Si varias pueden empezar el mismo día, se
escoge a quien tenga menos horas pendientes. De este modo, fases idénticas
en proyectos distintos se reparten y se adelantan lo máximo posible
aprovechando los huecos libres.

El trabajador **Unai** solo recibe tareas si se le asignan manualmente en la
lista de proyectos. El planificador automático lo ignora al repartir
fases por defecto.

Al planificar el montaje se respeta el orden en que cada trabajador termina
la fase de montaje de su proyecto anterior. Un nuevo montaje se coloca justo
después del último montaje programado para ese trabajador y aprovecha las
horas libres de ese mismo día hasta completar su jornada, salvo que la
prioridad del nuevo proyecto sea mayor y deba adelantarse en la cola.

De la misma forma, la fase de **soldar** puede empezar el mismo día que
termina el montaje si quedan horas disponibles. El planificador calcula las
horas libres que restan en la jornada y encadena la soldadura a continuación
sin sobrepasar nunca las ocho horas diarias. Las tareas de un mismo día se
ordenan según el momento en que se ejecutan, de modo que si otro trabajo de
dos horas cabe antes de soldar, se colocará en las primeras horas del día.

La fase **Pedidos**, realizada por Irene, se indica ahora mediante el campo
**Plazo acopio**. Esta fase abarca desde que termina el dibujo hasta la fecha
de acopio indicada y no se reparte por horas. Irene puede acumular tantos
proyectos como sea necesario dentro de ese margen sin limitación diaria.

Cada proyecto se colorea automáticamente con tonos claros para que el texto
sea legible en todas las vistas. Las tareas en el calendario muestran primero
el nombre del proyecto seguido del cliente y la fase para identificar mejor
cada entrada.

Al crear un proyecto puedes adjuntar una imagen opcional. Esta se guarda en
`static/uploads` y se muestra en el recuadro informativo que aparece al pulsar
una tarea en el calendario.
Ese mismo recuadro incluye ahora un botón **Reorganizar** que intenta
reubicar la fase seleccionada en el primer hueco libre disponible,
preferentemente antes de la fecha asignada. Si se encuentra un hueco
más temprano respetando todas las restricciones, el proyecto se guarda con
la nueva fecha de inicio y el calendario se actualiza al recargar la página.

También puedes arrastrar cualquier fase directamente sobre otra celda del
calendario. Al soltarla, la planificación mueve esa fase al día y trabajador
seleccionados, ajustando la fecha de inicio del proyecto para que la fase
comience en la nueva posición.
La fase movida aparece resaltada con un borde amarillo al recargar la página y
puedes deshacer el último movimiento pulsando **Ctrl+Z**, que la devolverá a su
fecha y trabajador anteriores.

El día actual aparece destacado con un borde rojo grueso en el calendario. Las
vistas de **Calendario** y **Completo** permiten plegar o desplegar las filas de
cada trabajador pulsando el símbolo situado junto a su nombre. Además, la lista
de proyectos incluye los mismos cuadros de búsqueda por proyecto y cliente que
el calendario, para filtrar rápidamente la información mostrada.
La sección de proyectos en la vista **Completo** puede plegarse o desplegarse
completamente pulsando el botón que aparece junto a su título.

Tanto en la pestaña **Proyectos** como en la vista **Completo** se muestra una
columna adicional que indica con un ✔ verde si cada proyecto llega a su fecha
límite o con una ❌ roja en caso contrario.

### Vacaciones

Desde la pestaña **Vacaciones** puedes registrar periodos de descanso para
cualquier trabajador seleccionándolo en la lista y especificando las fechas de
inicio y fin. Los días marcados como vacaciones aparecen rellenados en rojo en
el calendario y no admiten asignaciones de tareas. Si un trabajador tenía
proyectos planificados en esas fechas, la planificación se recalcula y esas
fases se reasignan automáticamente al trabajador disponible con menor carga. En
la lista de conflictos se añade una nota indicando los días de vacaciones, a qué
persona se han movido las tareas y si el proyecto sigue cumpliendo su fecha
límite tras el cambio. Aunque un trabajador tenga vacaciones cerca de la fecha
de inicio de un proyecto, no se descarta para nuevas fases: la planificación
simplemente saltará sus días libres y continuará al finalizar su descanso.
