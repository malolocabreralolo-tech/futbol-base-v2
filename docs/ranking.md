# Los mejores de cada año: cómo sale el ranking

La pantalla «Los mejores de cada año» (en Explorar, «Más») ordena a los niños nacidos el mismo año. Tiene
dos listas: **esta temporada** y **toda su trayectoria**. Este documento explica de dónde sale cada número,
en palabras de cualquiera. Las fórmulas exactas están en `scripts/ranking.py` (el índice) y en
`scripts/nacimiento.py` (el año de nacimiento); los números de aquí salen de esos dos ficheros.

## Qué mide

Mide **los goles**. Compara lo que marca cada niño con lo que marca un niño normal de su categoría, en la
misma temporada.

- **100 es la media.** Un niño que marca lo normal, en una liga normal y siendo de los mayores de su
  categoría, tiene 100.
- **200 es el doble de la media.** Y así.

Hay tres cosas que suben el índice:

1. **Marcar mucho por partido.**
2. **Marcar en una liga de más nivel.** Marcar en la Segunda Fase A vale más que en la E.
3. **Marcar siendo pequeño.** Vale más si el niño es de los pequeños de su categoría, o si juega con los
   mayores.

Y hay una corrección para quien ha jugado **pocos partidos**: así, tres goles en un partido no ponen a
nadie primero.

## La fórmula, con un ejemplo

Para cada temporada en la que ha jugado el niño:

> goles que cuentan = goles ÷ media de la categoría × nivel de la liga × premio por edad

La **media de la categoría** es lo que marca un niño normal en un partido de esa categoría y esa temporada.
Se calcula con todas las actas: todos los goles entre todos los partidos jugados por todos los niños.

Después se suma todo y se aplica la corrección de los pocos partidos:

> índice = 100 × (goles que cuentan + 6) ÷ (partidos + 6)

Los **6** son la corrección. Es como si a todos se les sumaran 6 partidos marcando justo la media. Con
muchos partidos, esos 6 casi no se notan. Con pocos, el índice se queda cerca de 100.

**Ejemplo, con números inventados.** Un niño nacido en 2017 juega en benjamín la temporada 2025-26, en la
Segunda Fase B. Juega 20 partidos y marca 15 goles. La media de benjamín ese año es 0,25 goles por partido.

- Goles frente a la media: 15 ÷ 0,25 = 60. Es decir, ha marcado lo que 60 partidos de un niño normal.
- Nivel de la Segunda Fase B: × 1,15, que da 69.
- Nacido en 2017, es de los pequeños de benjamín ese año: × 1,10, que da 75,9.
- Índice: 100 × (75,9 + 6) ÷ (20 + 6) = **315**.

Otro niño, de los mayores, en una liga normal, marca 3 goles en 3 partidos:

- 3 ÷ 0,25 = 12.
- Índice: 100 × (12 + 6) ÷ (3 + 6) = **200**.

Marca muchísimo por partido, pero ha jugado tan poco que la corrección lo frena.

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

**Cuidado: el año va sin comillas**, y el fichero tiene que ser JSON bien escrito. Si hay un error, la
pasada del bot se para. Así nunca se publica como confirmado un año mal escrito.

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
- **Un rival flojo no descuenta.** Un gol a un equipo que lo pierde todo vale lo mismo que a uno fuerte de
  la misma liga. Solo cuenta el nivel de la liga, no el del rival.
- **El año es una estimación.** Un niño mal estimado sale en un año que no es el suyo. Por eso existe la
  marca de año dudoso, y la forma de confirmarlo de arriba.
