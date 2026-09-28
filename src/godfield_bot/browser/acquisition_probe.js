// Passive, bounded transport. This script sends no requests or game commands.
(() => {
  const config = __GODFIELD_ACQUISITION_CONFIG__;
  const key = '__godfieldAcquisitionEvidenceV1';
  if (window[key]) return;
  const state = {
    streamId: window.crypto.randomUUID(), sequence: 0, acknowledged: 0,
    queue: [], dropped: 0, rejected: 0, hookErrors: 0,
    hookInstalled: false, registrations: 0,
  };
  Object.defineProperty(window, key, {value: state, configurable: false});
  const positive = (value) => Number.isSafeInteger(value) && value > 0 ? value : null;
  const nonnegative = (value) => Number.isSafeInteger(value) && value >= 0 ? value : null;
  const knownActions = new Set(config.event_actions);
  const boundActions = new Set(config.self_item_actions);
  const item = (raw, index) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('invalid item');
    return {
      raw_index: index, instance_id: positive(raw.id), model_id: positive(raw.modelId),
      fake_model_id: positive(raw.fakeModelId),
      used: typeof raw.used === 'boolean' ? raw.used : null,
    };
  };
  const items = (raw) => {
    if (!Array.isArray(raw) || raw.length > 512) throw new Error('invalid item array');
    return raw.map(item);
  };
  const capture = (document) => {
    try {
      const room = document && typeof document.data === 'function' ? document.data() : null;
      const game = room && room.game;
      if (!game || !Array.isArray(game.players)) return;
      const matches = game.players.filter((player) => player && player.name === config.identity);
      if (matches.length === 0) return;
      state.sequence += 1;
      if (matches.length !== 1) throw new Error('ambiguous self');
      const self = matches[0], selfId = positive(self.id);
      const gf = nonnegative(game.gf), update = nonnegative(game.updateCount);
      if (selfId === null || gf === null || update === null || game.players.length > 256)
        throw new Error('invalid version or self');
      const events = [], rawEvents = game.events;
      if (!Array.isArray(rawEvents) || rawEvents.length > 512) throw new Error('invalid events');
      let unreviewed = 0, redacted = 0;
      rawEvents.forEach((raw, index) => {
        if (!raw || typeof raw !== 'object' || !knownActions.has(raw.action)) {
          unreviewed += 1;
          return;
        }
        const actor = positive(raw.playerId);
        const bound = actor === selfId && boundActions.has(raw.action);
        const hasItems = raw.item != null || raw.items != null || raw.overflowItem != null ||
          raw.itemModelId != null;
        if (hasItems && !bound) redacted += 1;
        events.push({
          event_index: index, action: raw.action, player_id: actor,
          target_player_id: positive(raw.targetPlayerId), self_item_payload_bound: bound,
          item: bound && raw.item != null ? item(raw.item, 0) : null,
          items: bound && raw.items != null ? items(raw.items) : [],
          overflow_item: bound && raw.overflowItem != null ? item(raw.overflowItem, 0) : null,
          item_model_id: bound ? positive(raw.itemModelId) : null,
        });
      });
      const snapshot = {
        source_sequence: state.sequence, captured_at: new Date().toISOString(),
        field_number: gf, update_count: update, self_player_id: selfId,
        player_count: game.players.length,
        is_over: typeof game.isOver === 'boolean' ? game.isOver : null,
        attack_turn_player_id: positive(game.attackTurnPlayerId),
        self_items: items(self.items), events,
        unreviewed_event_count: unreviewed, redacted_item_event_count: redacted,
      };
      if (JSON.stringify(snapshot).length > 262144) throw new Error('snapshot budget');
      if (state.queue.length >= config.capacity) {
        state.queue.shift();
        state.dropped += 1;
      }
      state.queue.push(snapshot);
    } catch (_) {
      state.rejected += 1;
    }
  };
  const instrument = (firebase) => {
    if (!firebase || typeof firebase.onSnapshot !== 'function') return firebase;
    if (firebase.onSnapshot.__godfieldAcquisitionProbeWrapped) return firebase;
    const original = firebase.onSnapshot;
    const wrapped = function(...args) {
      for (let index = 1; index < args.length; index += 1) {
        const observer = args[index];
        if (typeof observer === 'function') {
          args[index] = function(snapshot, ...rest) {
            capture(snapshot);
            return observer.call(this, snapshot, ...rest);
          };
          break;
        }
        if (observer && typeof observer.next === 'function') {
          const replacement = {...observer};
          replacement.next = function(snapshot, ...rest) {
            capture(snapshot);
            return observer.next.call(observer, snapshot, ...rest);
          };
          for (const name of ['error', 'complete']) {
            if (typeof observer[name] === 'function')
              replacement[name] = (...values) => observer[name].apply(observer, values);
          }
          args[index] = replacement;
          break;
        }
      }
      state.registrations += 1;
      return original.apply(this, args);
    };
    Object.defineProperty(wrapped, '__godfieldAcquisitionProbeWrapped', {value: true});
    try {
      firebase.onSnapshot = wrapped;
      state.hookInstalled = firebase.onSnapshot === wrapped;
      if (!state.hookInstalled) state.hookErrors += 1;
    } catch (_) { state.hookErrors += 1; }
    return firebase;
  };
  // Chain an existing accessor (including the Dream probe) rather than replace
  // its assignment handling. Combined installation uses one ordered script.
  const previous = Object.getOwnPropertyDescriptor(window, 'firebase');
  let value = window.firebase;
  const getValue = () => previous && previous.get ? previous.get.call(window) : value;
  instrument(getValue());
  try { Object.defineProperty(window, 'firebase', {
    configurable: true, enumerable: true, get: getValue,
    set: (next) => {
      if (previous && previous.set) previous.set.call(window, next);
      else value = next;
      instrument(getValue());
    },
  }); } catch (_) { state.hookErrors += 1; }
})();
