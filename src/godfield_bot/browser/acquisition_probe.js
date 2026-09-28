// Passive, bounded transport. This script sends no requests or game commands.
(() => {
  const config = __GODFIELD_ACQUISITION_CONFIG__;
  const v2 = config.schema_version === 2;
  const key = v2 ? '__godfieldAcquisitionEvidenceV2' : '__godfieldAcquisitionEvidenceV1';
  if (window[key]) return;
  const state = {
    streamId: window.crypto.randomUUID(), sequence: 0, acknowledged: 0,
    queue: [], dropped: 0, rejected: 0, hookErrors: 0,
    hookInstalled: false, registrations: 0, schemaVersion: config.schema_version,
  };
  let previousPhase = null;
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
  const wireInteger = (raw, field) => {
    if (!Object.hasOwn(raw, field)) return 'missing';
    if (raw[field] === null) return 'null';
    if (positive(raw[field]) !== null) return 'positive_integer';
    return raw[field] === 0 ? 'zero' : 'other';
  };
  const wireItem = (raw, index) => ({
    raw_index: index, instance_id_kind: wireInteger(raw, 'id'),
    model_id_kind: wireInteger(raw, 'modelId'),
    fake_model_id_kind: wireInteger(raw, 'fakeModelId'),
    used_kind: !Object.hasOwn(raw, 'used') ? 'missing' : raw.used === null ? 'null' :
      typeof raw.used === 'boolean' ? 'boolean' : 'other',
  });
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
      const selfItems = items(self.items);
      let playerIds = [], selfWire = [], phaseBefore = null, phaseInput = 'initial', phaseStamp;
      if (v2) {
        playerIds = game.players.map((player) => positive(player && player.id)).sort((a,b) => a-b);
        if (playerIds.some((id) => id === null) || new Set(playerIds).size !== playerIds.length)
          throw new Error('invalid phase players');
        selfWire = self.items.map(wireItem);
        // No opponent models or arbitrary event fields enter this replay stamp.
        phaseStamp = JSON.stringify({gf, update, selfId, playerIds, selfItems, selfWire,
          events: rawEvents.map((raw) => raw && typeof raw === 'object' ?
            [typeof raw.action === 'string' && knownActions.has(raw.action) ? raw.action : null,
              positive(raw.playerId)] : null)});
        if (previousPhase) {
          const last = previousPhase.after;
          const samePlayers = selfId === last.self_player_id &&
            JSON.stringify(playerIds) === JSON.stringify(last.player_ids);
          if (samePlayers && gf === last.field_number && update === last.update_count) {
            phaseInput = previousPhase.stamp === phaseStamp ? 'repeat' : 'inconsistent_repeat';
            if (phaseInput === 'repeat') phaseBefore = previousPhase.before;
          } else if (samePlayers && gf >= last.field_number &&
                     update === last.update_count+1 && state.sequence === last.source_sequence+1) {
            phaseInput = 'consecutive'; phaseBefore = last;
          } else phaseInput = 'gap_or_boundary';
        }
      }
      let turn = phaseBefore ? phaseBefore.turn_player_id : null;
      let target = phaseBefore ? phaseBefore.target_player_id : null;
      const owners = [], unknownIndices = [];
      let unreviewed = 0, redacted = 0;
      rawEvents.forEach((raw, index) => {
        if (!raw || typeof raw !== 'object' || !knownActions.has(raw.action)) {
          unreviewed += 1;
          if (v2) { unknownIndices.push(index); turn = target = null; }
          return;
        }
        const actor = positive(raw.playerId);
        let owner = actor, basis = 'unresolved';
        if (v2) {
          const member = playerIds.includes(actor) ? actor : null;
          if (raw.action === 'advanceGF') { turn = member; target = null; }
          // The client keeps the opposite role on self-targets. Do not infer
          // a defender without a known attacker or treat a self-target as one.
          if (raw.action === 'setTargetPlayer')
            target = turn !== null && member !== turn ? member : null;
          owner = null;
          if (raw.action === 'gift' && member !== null) {
            owner = member; basis = 'explicit_gift_player';
          } else if (raw.action === 'useAttackItems' && turn !== null) {
            owner = turn; basis = 'turn_context';
          } else if (raw.action === 'useDefenseItems' && target !== null) {
            owner = target; basis = 'target_context';
          }
          owners.push({event_index: index, item_owner_player_id: owner, basis});
        }
        const bound = owner === selfId && boundActions.has(raw.action);
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
        if (v2 && !boundActions.has(raw.action) &&
            raw.action !== 'advanceGF' && raw.action !== 'setTargetPlayer') turn = target = null;
      });
      const snapshot = {
        source_sequence: state.sequence, captured_at: new Date().toISOString(),
        field_number: gf, update_count: update, self_player_id: selfId,
        player_count: game.players.length,
        is_over: typeof game.isOver === 'boolean' ? game.isOver : null,
        attack_turn_player_id: positive(game.attackTurnPlayerId),
        self_items: selfItems, events,
        unreviewed_event_count: unreviewed, redacted_item_event_count: redacted,
      };
      if (v2) {
        Object.assign(snapshot, {
          self_item_wire: selfWire, event_owners: owners, unreviewed_event_indices: unknownIndices,
          phase_input_status: phaseInput, phase_before: phaseBefore,
          phase_after: {source_sequence: state.sequence, update_count: update, field_number: gf,
            self_player_id: selfId, player_ids: playerIds, turn_player_id: turn, target_player_id: target},
        });
      }
      if (JSON.stringify(snapshot).length > 262144) throw new Error('snapshot budget');
      if (state.queue.length >= config.capacity) {
        state.queue.shift();
        state.dropped += 1;
      }
      state.queue.push(snapshot);
      if (v2) previousPhase = {before: phaseBefore, after: snapshot.phase_after, stamp: phaseStamp};
    } catch (_) {
      state.rejected += 1;
      previousPhase = null;
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
