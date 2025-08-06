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

Debajo del botón **Reportar bug** aparece otro llamado **Editar jornada laboral**.
Al pulsarlo se despliega una fila con un desplegable por día. Por defecto la fila
está oculta. Puedes elegir entre 1 y 9 horas de jornada (8 por defecto). Al
reducirlas, las horas que no quepan se trasladan al siguiente día libre sin
afectar a Irene ni a las fases de **mecanizar** y **tratamiento**.
Cuando cambias alguna jornada y la página se recarga, el calendario recuerda la
posición en la que estabas.

Los campos de fecha de los distintos formularios aparecen vacíos por defecto.
Puedes introducir las fechas como `dd-mm` o `dd/mm`; si no incluyes el año,
se tomará automáticamente el año en curso.

Todos los proyectos se guardan por defecto en `data/projects.json`. La
aplicación lee este archivo cada vez que se carga la página principal (la vista
**Completo**), de modo que si añades manualmente proyectos ahí también formarán
parte de la planificación. Si quieres conservar los datos en otra ubicación,
define la variable de entorno `EFIMERO_DATA_DIR` con la ruta a tu carpeta antes
de iniciar la aplicación.

La aplicación también puede recibir tarjetas desde Kanbanize mediante un webhook.
Si la tarjeta pertenece a la lane "Seguimiento compras", se guardará pero no
generará ningún proyecto.

 También puedes añadir **Hitos** indicando una descripción y una fecha. En ambas
 vistas de calendario aparece una gruesa línea roja a la derecha del día del
 hito y la descripción se muestra en rojo, en negrita y con un tamaño de letra
 el doble de grande dentro de su celda. Existe una pestaña **Hitos** que
 muestra la lista completa y permite eliminarlos con una **X** roja.

La pestaña **Completo** reúne todas las vistas en una sola página. En la
parte superior se muestran, de izquierda a derecha, el formulario de alta, el
de hitos y la lista de conflictos. Debajo aparecen el calendario y, al final,
la lista de proyectos. Cada sección se expande por
mpleto y la página ofrece una barra de desplazamiento vertical para consultar
la información cómodamente sin necesidad de reducir el zoom. Puedes desplazarte horizontalmente por el calendario
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
En la vista **Completo**, al pinchar en una fase no solo se destacan en el calendario
las tareas del mismo proyecto, sino que también se marca su fila correspondiente en la
tabla de proyectos mientras el resto aparece atenuado.
Además, cada conflicto que aparece en la lista muestra su texto en un cuadro centrado hasta que se cierre.
Por encima de la lista de **Conflictos** aparece un gran botón amarillo
**Reportar bug**. Es unas diez veces más grande que un botón normal para que
resulte muy visible. Al pulsarlo se abre un formulario donde debes indicar quién
registra la incidencia, en qué pestaña ocurrió, con qué frecuencia sucede y una
descripción detallada del problema. Todos los campos son obligatorios. Al
enviar el formulario se asigna un número de BUG y se intenta enviar un correo
con un resumen a `irodriguez@caldereria-cpk.es`. Puedes configurar el servidor
SMTP mediante las variables de entorno `BUG_SMTP_HOST`, `BUG_SMTP_PORT`,
`BUG_SMTP_USER`, `BUG_SMTP_PASS` y `BUG_SMTP_SSL` cuando sea necesario.

Todas las incidencias se almacenan también en un archivo y pueden consultarse
desde la pestaña **Bugs**, que muestra una tabla con su número, fecha,
usuario, pestaña y detalle.

Al crear nuevos proyectos, el planificador asigna cada fase a la persona
especializada en dicha tarea que pueda comenzarla antes. Los trabajadores
con esa fase en primer lugar tienen preferencia frente a quienes la
tienen en segundo o tercer puesto. Si varias personas con la misma
prioridad están libres el mismo día, se escoge a quien tenga menos horas
pendientes. De este modo, fases idénticas en proyectos distintos se
reparten y se adelantan lo máximo posible aprovechando los huecos libres.

El trabajador **Unai** solo recibe tareas si se le asignan manualmente en la
lista de proyectos. El planificador automático lo ignora al repartir
fases por defecto.

Las filas del calendario muestran a las personas siempre en este orden:
Pilar, Joseba 1, Irene, Mikel, Iban, Joseba 2, Naparra, Unai, Fabio, Beltxa,
Igor, Albi y Eneko. A partir del 21 de julio Igor deja de aparecer en el
calendario y ya no se le asignan nuevas fases.
Junto a cada nombre se indican entre paréntesis las fases que puede realizar en
su orden de prioridad para consultarlo de un vistazo.

Fabio se dedica exclusivamente a soldar, de modo que no puede recibir fases de
montaje.

La fila **Sin planificar** cuenta con todas las habilidades pero las trata por
igual sin prioridad entre ellas.

Además existe una fila adicional llamada **Sin planificar** donde se acumulan
las fases de los proyectos que no se quieran programar todavía. Estas tareas
se asignan siempre a partir del día de hoy. Aunque cada proyecto se reparte en
tramos de ocho horas diarias, la fila no tiene límite de jornada, por lo que
pueden coincidir tantos proyectos como se desee en el mismo día.
En el formulario de alta aparece una casilla **Planificar** marcada por
defecto. Si se desmarca, el nuevo proyecto se coloca en la fila *Sin
planificar* hasta que se decida moverlo manualmente. La tabla de proyectos
muestra una columna indicando con un ✔ verde si está planificado o una ❌ si
permanece sin planificar.
La vista **Completo** incorpora la misma columna y verifica realmente si
quedan fases en la fila *Sin planificar* para mostrar el estado correcto.
Las fases y los proyectos pueden arrastrarse libremente desde la fila
*Sin planificar* al calendario del resto de trabajadores y viceversa. Al
hacerlo la aplicación cambia automáticamente su estado de planificado para
mantener la coherencia.

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
Cada fase se programa en jornadas laborables consecutivas. Si un trabajador no
tiene libres esos días seguidos —incluyendo las jornadas posteriores a sus
montajes anteriores— se buscará otro que sí disponga de ese hueco antes de
dividir la tarea en intervalos separados.

La fase **Pedidos**, realizada por Irene, se indica ahora mediante el campo
**Plazo acopio**. Esta fase abarca desde que termina el dibujo hasta la fecha
de acopio indicada y no se reparte por horas. Si no se especifica un plazo, la
fase simplemente no se planifica. Irene puede acumular tantos proyectos como
sea necesario dentro de ese margen sin limitación diaria.

Las fases **mecanizar** y **tratamiento** funcionan de manera similar en
cuanto a capacidad: no existe un tope diario de proyectos asignados, pero cada
uno se planifica en bloques de ocho horas al día. Si una fase de tratamiento o
mecanizado dura más de ocho horas, se dividirá en jornadas consecutivas de
ocho horas hasta completarla.

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
Se ofrece también un botón rojo **Borrar fase** que elimina ese tramo de
la planificación tras una confirmación. Las demás fases de ese proyecto
permanecen en su sitio. Además, el recuadro incluye el botón **Sin planificar**
que asigna la fase seleccionada al día actual dentro de la fila *Sin planificar*
para reprogramarla más adelante.
Del mismo modo, el recuadro incluye **Dividir fase aquí**. Al pulsarlo,
la aplicación divide la duración de esa fase en dos mitades aunque la fecha
elegida no coincida exactamente con su mitad. La segunda parte se mantiene
como un tramo independiente y en las tablas de **Proyectos** aparece una
línea adicional con el mismo nombre, cliente y fecha límite mostrando las
horas restantes de esa fase.
Si posteriormente quieres revertir la operación, el mismo recuadro muestra
un botón **Deshacer división** que vuelve a unir ambas mitades sumando sus
horas. Se conserva el trabajador asignado a la parte mayor.
Tras dividir una fase puedes arrastrar cada mitad a un trabajador distinto
simplemente soltándola en la celda deseada. Las dos partes no tienen por qué
mantener un orden cronológico entre sí, pero la fecha elegida debe respetar el
final de la fase anterior.
Además se muestra un pequeño formulario con un campo de fecha y un botón
**Cambiar** para modificar manualmente el inicio de la fase. Si la fecha
introducida no es válida se despliega una alerta explicando el motivo.
Otro formulario permite editar la **fecha límite** del proyecto desde esa misma
ventana emergente o desde las tablas de proyectos, mostrando igualmente un
aviso si la nueva fecha no es correcta.

También puedes arrastrar cualquier fase directamente sobre otra celda del
calendario. Al soltarla, la planificación mueve esa fase al día y trabajador
seleccionados y guarda esa fecha como inicio manual de la fase. El resto del
proyecto no se recoloca automáticamente, de modo que pueden quedar días vacíos
entre una fase y la siguiente si así se desea.
La fase movida aparece resaltada con un grueso borde negro al recargar la página y
puedes deshacer el último movimiento pulsando **Ctrl+Z**, que la devolverá a su
fecha y trabajador anteriores.
Si la fase acaba programándose en una fecha distinta a la elegida al soltarla,
el calendario se desplazará automáticamente a ese nuevo día para que sea fácil
encontrarla y se mostrará una alerta indicando por qué no pudo quedarse en la
celda seleccionada.
Durante este proceso se validan tres aspectos: el trabajador debe tener esa
fase entre sus habilidades, el día escogido no puede coincidir con sus
vacaciones (salvo en el caso de Irene, que puede trabajar igualmente de lunes a
viernes) y la fase no se puede adelantar a la inmediatamente anterior.
El resaltado negro permanece hasta que se mueva otra fase.

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
Desde esas mismas tablas puedes cambiar manualmente la fecha de inicio de
cualquier fase mediante los campos de fecha que aparecen junto a cada
trabajador asignado. Si la fecha introducida no es válida, la página mostrará
una alerta explicando el motivo.

### Vacaciones

Desde la pestaña **Vacaciones** puedes registrar periodos de descanso para
cualquier trabajador seleccionándolo en la lista y especificando las fechas de
inicio y fin. Los días marcados como vacaciones aparecen rellenados en rojo y el
bloque ocupa toda la celda del calendario, sin dejar huecos. No admiten
asignaciones de tareas, excepto en el caso de **Irene**, que puede recibir
trabajo esos días mientras no caigan en fin de semana. Sus vacaciones siguen
mostrándose en el calendario aunque no influyan en la planificación. Si un trabajador tenía
proyectos planificados en esas fechas, la planificación se recalcula y esas
fases se reasignan automáticamente al trabajador disponible con menor carga. En
la lista de conflictos se añade una nota indicando los días de vacaciones, a qué
persona se han movido las tareas y si el proyecto sigue cumpliendo su fecha
límite tras el cambio. Aunque un trabajador tenga vacaciones cerca de la fecha
de inicio de un proyecto, no se descarta para nuevas fases: la planificación
simplemente salta sus días libres y continúa al finalizar su descanso. Si el
periodo de la fase solo incluye un día de vacaciones, se sigue asignando a ese
trabajador y la tarea se retoma tras su ausencia.
