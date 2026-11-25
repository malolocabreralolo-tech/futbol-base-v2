# Los mejores de cada año: cómo sale el ranking

La pantalla «Los mejores de cada año» (en Explorar, «Más») ordena a los niños nacidos el mismo año. Tiene
dos listas: **esta temporada** y **toda su trayectoria**. Este documento explica de dónde sale cada número,
en palabras de cualquiera. Las fórmulas exactas están en `scripts/ranking.py` (el índice) y en
`scripts/nacimiento.py` (el año de nacimiento); los números de aquí salen de esos dos ficheros.

## Qué mide

Mide **los goles**. Compara lo que marca cada niño con lo que marca un niño normal de su categoría, en la
misma temporada.

- **100 es la media.** Un niño que marca lo normal, a rivales normales, en una liga normal de Gran Canaria
  y siendo de los mayores de su categoría, tiene cerca de 100: el puesto de su equipo lo mueve un poco
  arriba o abajo.
- **200 es el doble de la media.** Y así.

Es más difícil destacar en un equipo bueno y en una liga buena que en un equipo malo y en una liga mala.
Por eso **un gol no vale lo mismo en todas partes**. Hay cinco cosas que suben el índice:

1. **Marcar mucho por partido.**
2. **Marcar a rivales que encajan poco.** Un gol a un equipo que casi no encaja en toda su temporada vale
   más que uno al que lo encaja todo.
3. **Marcar en una liga de más nivel.** Marcar en la Segunda Fase A vale más que en la E, y en Gran Canaria
   más que en Lanzarote o Fuerteventura. Y los goles de la primera fase de un equipo que la federación puso
   después en la A valen como de la A.
4. **Marcar en un equipo de los de arriba.** Su equipo es de los primeros de su grupo.
5. **Marcar siendo pequeño.** Vale más si el niño es de los pequeños de su categoría, o si juega con los
   mayores.

Y hay una corrección para quien ha jugado **pocos partidos**: así, tres goles en un partido no ponen a
nadie primero.

## La fórmula, con un ejemplo

Primero, cada gol se multiplica por **el peso de su rival** en ese partido (la tabla de más abajo). La suma
son sus **goles por rival**. Después, para cada temporada y cada grupo en el que ha jugado el niño:

> goles que cuentan = goles por rival ÷ media de la categoría × nivel de la liga × nivel de la isla × nivel
> del equipo × premio por edad

La **media de la categoría** es lo que marca un niño normal en un partido de esa categoría y esa temporada.
Se calcula con todas las actas: todos los goles (los de verdad, sin el peso del rival) entre todos los
partidos jugados por todos los niños.

Después se suma todo y se aplica la corrección de los pocos partidos:

> índice = 100 × (goles que cuentan + 6) ÷ (partidos + 6)

Los **6** son la corrección. Es como si a todos se les sumaran 6 partidos marcando justo la media. Con
muchos partidos, esos 6 casi no se notan. Con pocos, el índice se queda cerca de 100.

**Ejemplo, con números inventados.** Un niño nacido en 2017 juega en benjamín la temporada 2025-26, en la
Segunda Fase B de Gran Canaria, en el equipo que va primero de su grupo. Juega 20 partidos y marca 15
goles: 10 a rivales que encajan lo normal y 5 al que menos encaja del grupo. La media de benjamín ese año
es 0,25 goles por partido.

- Goles por rival: 10 × 1 + 5 × 1,5 = 17,5.
- Frente a la media: 17,5 ÷ 0,25 = 70. Es decir, ha marcado lo que 70 partidos de un niño normal.
- Nivel de la Segunda Fase B: × 1,15, que da 80,5. Gran Canaria: × 1,00.
- Su equipo es el primero: × 1,15, que da 92,6.
- Nacido en 2017, es de los pequeños de benjamín ese año: × 1,10, que da 101,8.
- Índice: 100 × (101,8 + 6) ÷ (20 + 6) = **415**.

Otro niño, de los mayores, en una liga normal de Gran Canaria y en un equipo de mitad de tabla, marca 3
goles en 3 partidos a rivales normales:

- 3 ÷ 0,25 = 12; mitad de tabla, × 1,025: 12,3.
- Índice: 100 × (12,3 + 6) ÷ (3 + 6) = **203**.

Marca muchísimo por partido, pero ha jugado tan poco que la corrección lo frena.

## El peso del rival

Se mira **cuántos goles encaja el rival por partido en toda su temporada** de esa categoría: todos sus
partidos con marcador, sean de la primera fase, de las eliminatorias, de la segunda fase o de una copa. Y se
mira **con prudencia**: a lo que ha encajado se le suman 4 partidos encajando justo la media. Así, un rival
que solo ha jugado un partido se queda casi en la media (una goleada suelta no dice mucho) y uno que lleva
veinte pesa por lo que ha hecho.

> lo que encaja el rival = (goles en contra + 4 × media) ÷ (partidos + 4)

La **media** es lo que encaja un equipo por partido en esa temporada y categoría (todos los goles entre dos
veces todos los partidos). Un gol vale la media dividida entre lo que encaja el rival, con un mínimo de 0,5 y
un máximo de 1,5. Por ejemplo, con una media de 2 goles por partido:

| El rival… | Encaja (con prudencia) | Un gol vale |
|---|---|---|
| no ha jugado ningún partido | 2,0 | × 1,00 |
| ha jugado 1 y encajó 3 | (3 + 8) ÷ 5 = 2,2 | × 0,91 |
| ha jugado 1 y encajó 20 | (20 + 8) ÷ 5 = 5,6 | × 0,50 |
| ha jugado 20 y encajó 20 | (20 + 8) ÷ 24 = 1,17 | × 1,50 |
| ha jugado 20 y encajó 40 | (40 + 8) ÷ 24 = 2,0 | × 1,00 |
| ha jugado 20 y encajó 60 | (60 + 8) ÷ 24 = 2,83 | × 0,71 |

## El nivel de la liga

Sale del nombre de la fase del grupo.

| Fase | Nivel |
|---|---|
| Segunda Fase A | 1,30 |
| Segunda Fase B | 1,15 |
| Segunda Fase C | 1,05 |
| Segunda Fase D | 1,00 |
| Segunda Fase E | 0,95 |
| Segunda Fase con otra letra (F, G…) | 0,90 |
| Preferente | 1,25 |
| Copa de Campeones (sin letra) | 1,25 |
| Todo lo demás (Primera Fase, ligas de isla, copas…) | 1,00 |

Si la Copa de Campeones lleva letra (A a E), vale lo mismo que esa letra en la Segunda Fase.

Una copa que lleva «Preferente» en medio del nombre (por ejemplo, «Copa Cabildo Preferente Lanzarote») no
cuenta como Preferente: vale 1,00, porque en una copa se mezclan equipos de varios niveles.

**Los grupos sin nivel propio** (la Primera Fase, las eliminatorias, una copa o una liga de isla) cuentan
como **la Segunda Fase en la que la federación puso a su equipo** esa temporada: el equipo bueno es el que
acabó en la A. Los goles de la primera fase y de las eliminatorias de un equipo que está en la Segunda Fase A
valen como de la A (1,30), y los de uno que está en la F, como de la F (0,90). Basta con que el equipo esté en
ese grupo (en su clasificación o en su calendario), aunque aún no haya jugado. Un equipo que no está en
ninguna Segunda Fase con letra se queda con el nivel de su grupo (1,00). Los grupos con nivel propio
(Segunda Fase con letra, Preferente, Copa de Campeones) valen lo suyo.

Y se multiplica por **el nivel de la isla** del grupo:

| Isla | Nivel |
|---|---|
| Gran Canaria | 1,00 |
| Lanzarote | 0,85 |
| Fuerteventura | 0,85 |

Así, la Preferente de Lanzarote vale 1,25 × 0,85 = 1,06.

## El nivel del equipo

Se ordenan los equipos del grupo por **puntos por partido** (a igualdad, por diferencia de goles por
partido). El primero vale × 1,15 y el último × 0,90; los demás, en medio, según su puesto. En un grupo de
cinco:

| Puesto | Nivel |
|---|---|
| 1.º | 1,15 |
| 2.º | 1,0875 |
| 3.º | 1,025 |
| 4.º | 0,9625 |
| 5.º | 0,90 |

Solo cuentan los equipos con **3 partidos o más** con marcador. Un equipo con menos, o un grupo en el que
solo hay uno que llegue, vale × 1,00 (pasa en las copas cortas y al principio de la temporada).

## El premio por edad

Cada categoría admite dos o tres años de nacimiento. El premio depende de cuántos años es el niño más joven
que los mayores que admite su categoría esa temporada.

| El niño es… | Premio |
|---|---|
| De los mayores de la categoría (o más mayor) | × 1,00 |
| Un año más joven que los mayores (de los pequeños) | × 1,10 |
| Dos años más joven (juega con los mayores) | × 1,25 |
| Tres años o más (dos categorías por encima de la suya) | × 1,40 |

## Quién sale en cada lista

- **Esta temporada:** quien tiene al menos **3 partidos** esta temporada. Solo cuentan sus partidos de esta
  temporada.
- **Toda su trayectoria:** quien tiene al menos **10 partidos** en total. Cuenta todo lo que ha jugado.
- Como mucho salen **100 niños** por lista.
- Para ordenar: primero el índice y, a igual índice, más goles.
- Al principio de una temporada, la lista de «esta temporada» tiene poca gente: casi nadie llega todavía a
  los 3 partidos.

## De dónde sale el año de nacimiento

**Nadie publica la fecha de nacimiento**: ni la federación ni las actas. La web la **estima** por las
categorías en las que ha jugado el niño. Por eso siempre dice «(estimado)», salvo que el año esté confirmado
(más abajo).

Cada categoría admite unos años de nacimiento. En la temporada 2025-26:

| Categoría | Nacidos en |
|---|---|
| Miniprebenjamín (solo en la liga de escuelas) | 2020 o 2021 |
| Prebenjamín | 2018 o 2019 |
| Benjamín | 2016 o 2017 |
| Alevín | 2014 o 2015 |
| Infantil | 2012 o 2013 |
| Cadete | 2010 o 2011 |
| Juvenil | 2007, 2008 o 2009 |

Cada temporada, todo se mueve un año.

**Una sola temporada deja dos años posibles.** Varias temporadas se cruzan y van cerrando la ventana.

**Ejemplo inventado:** un niño juega en prebenjamín en 2024-25 (2017 o 2018) y en benjamín en 2025-26
(2016 o 2017). El único año que encaja con las dos es 2017.

**La liga de escuelas también cuenta.** Si la ficha está enlazada con la liga de escuelas (MyGol: el
mismo nombre y los dos apellidos, y solo cuando no hay duda; [mygol.md](mygol.md)), cada temporada de escuela
es una más para el año, con las jornadas que jugó (una temporada en la plantilla sin ninguna jugada
apuntada cuenta poco). Como muchos niños pasan por la escuela antes de federarse, suele cerrar la duda: de
las fichas enlazadas que tenían dos años posibles, unas cinco de cada seis pasan a uno. En el ranking la
escuela no suma nada (no tiene goles): solo cambia en qué lista de año sale el niño.

No es un simple cruce. Un niño puede jugar una temporada con los mayores, y un acta puede estar mal. Por
eso la web no descarta nada: lo que no encaja lo hace menos probable. Y una temporada entera pesa más que
dos partidos sueltos.

Al final quedan **de uno a tres años**:

- Con **uno**, la ficha dice «Nacido en 2017 (estimado)».
- Con **dos**, «Nacido en 2016 o 2017 (estimado)». En el ranking, ese niño sale en las dos listas (en la de
  2016 y en la de 2017), con la marca «año dudoso». Su índice puede cambiar de una a otra, porque el premio
  por edad depende del año.
- Con **tres**, «Nacido entre 2007 y 2009 (estimado)». Pasa en juvenil, que admite tres años, y con
  algún niño cuyas categorías no encajan del todo.
- Un niño que solo ha jugado en categorías que la web no conoce no tiene año, y la ficha no lo dice.

## Cómo confirmar el año de un niño

Si se sabe el año de un niño por una fuente pública (por ejemplo, una noticia del club), se puede
confirmar.

1. Busca la **clave** de su ficha. Está en la dirección de su página en la web: lo que va detrás de
   `#/jugador?id=`. Puede ser un número (el identificador de la federación) o una `n` seguida de 9 letras y
   cifras.
2. Añádela al fichero `scripts/anios_confirmados.json`. Hoy está vacío (`{}`). Por ejemplo, con dos claves
   inventadas:

   ```json
   {
     "n0abc12345": {"anio": 2016, "fuente": "Noticia del club, 12/10/2026"},
     "n0ejemplo1": {"anio": 2015, "fuente": "Web del club"}
   }
   ```

3. Súbelo. En la siguiente pasada del bot:
   - la ficha dirá «Nacido en 2016», sin «(estimado)»;
   - el niño saldrá solo en el ranking de ese año, sin la marca de año dudoso.

**Cuidado: el año va sin comillas**, y el fichero tiene que ser JSON bien escrito. Si hay un error, aunque
sea en una sola entrada, el bot no se para: avisa en su salida («anios_confirmados.json no se entiende») y
publica sin **ningún** año confirmado hasta que se corrija. Así nunca se publica como confirmado un año mal
escrito.

La clave de un alias (una ficha antigua que se unió a otra) también vale: confirma el año de la ficha a la
que lleva.

## Lo que el ranking no puede ver

El ranking sale **solo de las actas de la federación**. Las actas dicen quién jugó y quién marcó, y poco
más. Por eso:

- **No hay minutos.** Un niño que entra un minuto cuenta un partido entero, igual que el que juega todo. Y
  un suplente convocado cuenta como partido jugado, aunque no salga al campo: el acta no dice si salió.
- **No se sabe quién es portero ni defensa.** El acta no dice la posición. El ranking **favorece a quien
  marca**. Un buen portero o un buen defensa casi nunca saldrá arriba.
- **Hay goles sin dueño.** La federación publica unos **4.700 goles** con «sin nombre publicado» (el club
  no autoriza el nombre). Esos goles no se pueden dar a ningún niño.
- **Solo cuentan los partidos con acta**, desde la temporada **2019-20**. Lo que se jugó antes, o los
  partidos sin acta, no cuentan.
- **El nivel de las islas es una apreciación fija**, no una medida. Lanzarote y Fuerteventura valen 0,85
  porque sus ligas tienen menos equipos y menos nivel, pero los equipos de islas distintas casi nunca juegan
  entre sí, así que las actas no dejan medirlo.
- **El rival se mide con su temporada en la categoría, no con el nivel de su liga.** Un rival que encaja
  poco en una liga floja pesa como uno que encaja poco en una fuerte; la diferencia entre ligas la pone el
  nivel de la liga.
- **El año es una estimación.** Un niño mal estimado sale en un año que no es el suyo. Por eso existe la
  marca de año dudoso, y la forma de confirmarlo de arriba.
