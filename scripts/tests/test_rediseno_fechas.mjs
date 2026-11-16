// El «hoy» de la app es el de Canarias (decisión 4, M1 de B1).
import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { canaryTodayISO } from '../../src/links.js';

test('canaryTodayISO: la fecha de Canarias, verano (UTC+1) e invierno (UTC+0)', () => {
  assert.equal(canaryTodayISO(new Date('2026-09-23T22:30:00Z')), '2026-09-23', '23:30 en Canarias');
  assert.equal(canaryTodayISO(new Date('2026-09-23T23:00:00Z')), '2026-09-24', 'medianoche en Canarias');
  assert.equal(canaryTodayISO(new Date('2026-01-10T23:59:00Z')), '2026-01-10');
  assert.equal(canaryTodayISO(new Date('2026-01-11T00:00:00Z')), '2026-01-11');
  assert.match(canaryTodayISO(), /^\d{4}-\d{2}-\d{2}$/, 'sin argumentos, el reloj de ahora');
});

test('canaryTodayISO: un móvil con hora peninsular no adelanta el día (M1)', () => {
  const tz = process.env.TZ;
  process.env.TZ = 'Europe/Madrid';
  try {
    const now = new Date('2026-09-23T22:30:00Z');       // 00:30 del 24 en Madrid
    assert.equal(now.getDate(), 24, 'el reloj del dispositivo ya está en mañana');
    assert.equal(canaryTodayISO(now), '2026-09-23');
    assert.equal(canaryTodayISO(now, 'Europe/Madrid'), '2026-09-24', 'la zona es la del parámetro');
  } finally {
    if (tz === undefined) delete process.env.TZ;
    else process.env.TZ = tz;
  }
});
