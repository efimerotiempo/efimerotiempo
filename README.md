## Planificador de proyectos

Esta aplicación web permite introducir proyectos y planificar automáticamente sus
fases utilizando la disponibilidad de los trabajadores.

### Uso rápido

```bash
pip install flask
python app.py
```

Visita `http://localhost:5000` en tu navegador para ir directamente a la vista
**Completo**, que combina el calendario y los proyectos.
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
Si la tarjeta pertenece a la lane "Seguimiento Compras", se guardará para el
calendario de pedidos siempre que su columna no sea "Material taller",
"Material cliente", "Tratamiento final", "Pdte. Verificación",
"Material Recepcionado" o "Ready to Archive". Las tarjetas sin `deadline`
aparecen en la columna lateral **Sin fecha de entrega confirmada**, y sólo se
visualizan proyectos de esta misma lane. En ningún caso generará un proyecto.
Si una tarjeta de proyecto pasa a la columna "Ready to Archive", el
Planificador eliminará automáticamente el proyecto y sus fases.
 También puedes añadir **Notas** indicando una descripción y una fecha. En ambas
 vistas de calendario aparece una gruesa línea roja a la derecha del día de la
 nota y la descripción se muestra en rojo y en negrita al final del calendario,
 con un tamaño de letra la mitad de grande que el resto de celdas. Si hay varias
 notas para el mismo día, se apilan en líneas separadas. Existe una pestaña
 **Notas** que muestra la lista completa y permite eliminarlas con una **X** roja.

La pestaña **Observaciones** lista todos los proyectos que contienen texto en ese
campo y desde ella se pueden editar o borrar esas observaciones.

La pestaña **Completo** reúne todas las vistas en una sola página. En la
parte superior se muestran el formulario de notas y la lista de conflictos.
Debajo aparecen el calendario y, al final,
la lista de proyectos. Cada sección se expande por completo y la página ofrece una barra de desplazamiento vertical para consultar la información cómodamente sin necesidad de reducir el zoom. Puedes desplazarte horizontalmente por el calendario
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
 ha producido. Si desde el calendario se eliminan todas las fases de un proyecto,
 este también desaparece automáticamente de las listas de proyectos en todas las
 pestañas.
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

Al crear nuevos proyectos, todas las fases se asignan por defecto a **Sin
planificar**. Desde la tabla de proyectos o el calendario puedes moverlas a
cualquier trabajador sin restricciones de habilidades; el planificador solo
considera su disponibilidad para colocarlas lo antes posible.

El trabajador **Unai** solo recibe tareas si se le asignan manualmente en la
lista de proyectos. Las fases sin trabajador asignado se marcan como **Sin
planificar** y permanecen en la columna lateral hasta que se asignen
manualmente.

Las filas del calendario muestran a las personas siempre en este orden:
Pilar, Joseba 1, Irene, Mikel, Iban, Joseba 2, Naparra, Unai, Fabio, Beltxa,
Igor, Albi y Eneko. A partir del 21 de julio Igor deja de aparecer en el
calendario y ya no se le asignan nuevas fases.

Junto al calendario hay una columna llamada **Fases sin planificar** que
reúne todas las fases pendientes. Cada proyecto aparece como una carpeta con
su nombre y cliente; las carpetas están plegadas por defecto y se pueden
desplegar para ver y arrastrar sus fases al calendario. Dentro de cada proyecto
las horas de una misma fase se agrupan y se muestran como una única entrada con
el total pendiente. La columna comienza con 2500 px de ancho pero puede
ampliarse o reducirse sin límite arrastrando su borde izquierdo y se sitúa a la
derecha del todo, fuera del área
desplazable del calendario. El ancho elegido se mantiene al cambiar de pestaña
y volver a **Completo**. Un botón «Fases sin planificar» flotante permite
mostrar de nuevo la columna cuando se oculta. Las carpetas se ordenan por la
fecha **Material confirmado** de cada proyecto y una división separa los que
cuentan con esa fecha de los que no. El título de cada carpeta muestra la
**Fecha límite** del proyecto tras el nombre del cliente, y se actualiza si
cambia.

La tabla de proyectos muestra, a la derecha de **Fecha límite**, la columna
**Fecha material confirmado**, e incluye una columna indicando con un ✔ verde
si está planificado o una ❌ si permanece sin planificar. A continuación se
encuentra la columna **Imagen**, que permite abrir cada archivo cargado en una
nueva pestaña. Además, al pulsar una fase en el calendario se visualizará la
primera imagen adjunta como enlace clicable que abre la imagen original en una
nueva pestaña, igual que si se hubiera cargado manualmente. La columna inicial
del calendario muestra únicamente el nombre de cada persona y permanece fija a
la izquierda para que siempre sea visible. La fecha de material confirmado
también se visualiza en la ventana emergente al pulsar cualquier fase, tanto en
el calendario como en la columna de fases sin planificar. Si se programa una
fase en una fecha anterior a la de material confirmado, la planificación se
realiza igualmente sin mostrar avisos adicionales.

Si una tarjeta tiene su **fecha límite** confirmada (campo "fecha tope"),
al planificar una fase que exceda esa fecha se mostrará una ventana
emergente en naranja con el aviso **FECHA LÍMITE CONFIRMADA A CLIENTE, NO
SOBREPASAR.** junto con el proyecto, el cliente y el día límite, aunque la
planificación continúa.

Al planificar el montaje se respeta el orden en que cada trabajador termina
la fase de montaje de su proyecto anterior. Un nuevo montaje se coloca justo
después del último montaje programado para ese trabajador y aprovecha las
horas libres de ese mismo día hasta completar su jornada, salvo que la
prioridad del nuevo proyecto sea mayor y deba adelantarse en la cola.

De la misma forma, la fase de **soldar 2º** puede empezar el mismo día que
termina el montaje si quedan horas disponibles. El planificador calcula las
horas libres que restan en la jornada y encadena la soldadura a continuación
sin sobrepasar nunca las ocho horas diarias. Las tareas de un mismo día se
ordenan según el momento en que se ejecutan, de modo que si otro trabajo de
dos horas cabe antes de soldar 2º, se colocará en las primeras horas del día.
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

Se ofrece un botón rojo **Borrar fase** que elimina ese tramo de
la planificación tras una confirmación. Las demás fases de ese proyecto
permanecen en su sitio. Si se borran todas las fases de un proyecto, este se
elimina automáticamente. Además, el recuadro incluye el botón **Sin planificar**
que asigna la fase seleccionada al día actual dentro de la columna *Fases sin
planificar* para reprogramarla más adelante.
Del mismo modo, el recuadro incluye **Dividir fase aquí**. Al pulsarlo se abre
una ventana donde puedes indicar cuántas horas dedicar a la primera y a la
segunda parte de la fase. Cada tramo se guarda como independiente y en las
tablas de **Proyectos** aparece una línea adicional con el mismo nombre,
cliente y fecha límite mostrando las horas restantes de esa fase.
Si posteriormente quieres revertir la operación, el mismo recuadro muestra
un botón **Deshacer división** que vuelve a unir ambas partes sumando sus
horas. Se conserva el trabajador asignado a la parte mayor.
Tras dividir una fase puedes arrastrar cada mitad a un trabajador distinto
simplemente soltándola en la celda deseada. Las dos partes no tienen por qué
mantener un orden cronológico entre sí y, al mover la segunda, se respeta
exactamente la fecha que selecciones aunque haya huecos libres antes.
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
Durante este proceso se validan dos aspectos: el día escogido no puede
coincidir con las vacaciones del trabajador y la fase no se puede adelantar a
la inmediatamente anterior.
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
asignaciones de tareas y la planificación simplemente salta esos días,
continuando cuando el trabajador regresa de su descanso. En el calendario puedes
pulsar sobre un día de vacaciones para mostrar una X roja y eliminarlo.
La lista oculta automáticamente las vacaciones cuyo periodo ya ha finalizado.

### Recursos

La pestaña **Recursos** muestra la lista de trabajadores con una casilla para
activar o desactivar su visualización. Las filas desmarcadas desaparecen del
calendario hasta que se vuelvan a marcar.
