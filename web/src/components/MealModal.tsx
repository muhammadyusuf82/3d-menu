import { useEffect, useMemo, useRef, useState } from 'react';
import { priceCart, mealPromo } from '../../../shared/pricing.ts';
import { useApp } from '../store.tsx';
import { formatMoney, loc, toPriceable } from '../lib/menu.ts';
import { eventLabel } from '../lib/eventText.ts';
import { BigViewer, miniManager, type ModelState } from '../three/viewer.ts';
import { hasPhotoModel, photoCredit } from '../three/photoreal.ts';
import { Dialog } from './common.tsx';

const reduce = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

export function MealModal({ mealId, onClose }: { mealId: string; onClose: () => void }) {
  const { snap, t, lang, now, catsById, quality, setQuality, addToCart, toast } = useApp();
  const meal = snap!.meals.find((m) => m.id === mealId)!;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewer = useRef<BigViewer | null>(null);
  const qualityRef = useRef(quality);
  qualityRef.current = quality;
  const spinRef = useRef(true);
  const [qty, setQty] = useState(1);
  const [exploded, setExploded] = useState(false);
  const [spinning, setSpinning] = useState(!reduce());
  const [failed, setFailed] = useState(false);
  const [model, setModel] = useState<ModelState>({ photo: false, available: hasPhotoModel(mealId), loading: false, failed: false, explodable: true });
  spinRef.current = spinning;

  // thumbnails stop rendering while the large viewer is open
  useEffect(() => { miniManager.paused = true; return () => { miniManager.paused = false; }; }, []);

  const mealKey = JSON.stringify([meal.ingredients, meal.model]);
  useEffect(() => {
    try {
      const v = new BigViewer(canvasRef.current!, {
        onUserInteract: () => setSpinning(false),
        onSlow: () => { setQuality('standard'); toast(t('hdSlow'), 'info'); },
        onModelState: (s) => { setModel(s); if (!s.loading) setExploded(false); },
      });
      viewer.current = v;
      v.setMeal(meal, qualityRef.current, spinRef.current);
      setExploded(false);
      setFailed(false);
      return () => { v.destroy(); viewer.current = null; };
    } catch {
      setFailed(true);
      return undefined;
    }
    // rebuild only when the model itself changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mealKey, meal.id]);

  useEffect(() => { viewer.current?.setQuality(quality); }, [quality]);

  const events = snap!.events;
  const promo = mealPromo(toPriceable(meal, catsById), events, now);
  const total = useMemo(
    () => priceCart([{ meal: toPriceable(meal, catsById), qty }], events, now).total,
    [meal, catsById, qty, events, now],
  );
  const name = loc(meal.name, lang);
  const unit = (u: string) => (u === 'g' ? t('unit_g') : u === 'ml' ? t('unit_ml') : u === 'pcs' ? t('pcs') : t('slices'));

  return (
    <Dialog onClose={onClose} className="meal-dialog" label={name}>
      <div className="shell">
        <button className="modal-close" onClick={() => (document.querySelector('dialog.meal-dialog') as HTMLDialogElement | null)?.close()} aria-label={t('close')}>✕</button>
        <div className="stage">
          <canvas ref={canvasRef} aria-label={t('modelLabel')} />
          {failed && (
            <div className="stage-fallback">
              <div>
                <span className="fallback-icon" aria-hidden="true">{catsById.get(meal.categoryId)?.icon ?? '🍽️'}</span>
                <b>{t('unavailable3d')}</b>
                <p>{t('fallbackDesc')}</p>
              </div>
            </div>
          )}
          <div className="stage-top">
            <div className="stage-title"><span>{model.photo ? t('photoModel') : t('liveModel')}</span><h4>{name}</h4></div>
            {!failed && (
              <div className="stage-controls">
                <button className="sbtn" aria-pressed={quality === 'hd'} title={t('hdHint')} onClick={() => setQuality(quality === 'hd' ? 'standard' : 'hd')}>✦ HD</button>
                <button className="sbtn" aria-pressed={spinning} onClick={() => { const n = !spinning; setSpinning(n); viewer.current?.spin(n); }}>⟳ {t('autoSpin')}</button>
                <button className="sbtn" aria-pressed={exploded} disabled={!model.explodable} title={model.explodable ? undefined : t('hdSolid')}
                  onClick={() => { const n = !exploded; setExploded(n); viewer.current?.explode(n); }}>{exploded ? t('assemble') : t('explode')}</button>
                <button className="sbtn" onClick={() => { setExploded(false); viewer.current?.reset(); }}>⤢ {t('resetView')}</button>
              </div>
            )}
          </div>
          {!failed && quality === 'hd' && (
            <div className="stage-note" role="status">
              {model.loading ? <><span className="spinner" aria-hidden="true" /> {t('hdLoading')}</>
                : model.failed ? t('hdFailed')
                : !model.available ? t('hdNotAvailable')
                : model.photo && !model.explodable ? t('hdSolid')
                : null}
            </div>
          )}
          <div className="stage-bottom">{t('modelHint')}{model.photo && <> · <span className="credit">{t(photoCredit(meal.id))}</span></>}</div>
        </div>
        <aside className="info">
          <div className="info-head">
            <span className="tag">{loc(catsById.get(meal.categoryId)?.name ?? ['', ''], lang)}</span>
            <h2>{name}</h2>
            <p>{loc(meal.desc, lang)}</p>
            {promo && <p className="promo-line">🔥 {loc(promo.event.title, lang)} · <b>{eventLabel(promo.event, t, lang)}</b></p>}
          </div>
          <div className="facts">
            <div className="fact"><span>{t('prepTime')}</span><b>{meal.prepMin} {t('min')}</b></div>
            <div className="fact"><span>{t('energy')}</span><b>{meal.kcal} {t('kcal')}</b></div>
            <div className="fact"><span>{t('price')}</span><b>{formatMoney(promo?.discountedPrice ?? meal.price, lang)}</b></div>
          </div>
          <h3>{t('recipe')}</h3>
          <ul className="ing-list">
            {meal.ingredients.map((i) => (
              <li key={i.id}>
                <button
                  className="ing-btn"
                  onPointerOver={() => viewer.current?.highlight(i.id, true)} onPointerOut={() => viewer.current?.highlight(i.id, false)}
                  onFocus={() => viewer.current?.highlight(i.id, true)} onBlur={() => viewer.current?.highlight(i.id, false)}
                  onClick={() => viewer.current?.focus(i.id)}
                >
                  <span className="dot" style={{ backgroundColor: i.color }} />
                  <span className="iname">{loc(i.name, lang)}</span>
                  <span className="iamt">{i.amount} {unit(i.unit)}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="info-foot">
            <div className="qty">
              <button aria-label={t('decrease')} disabled={qty === 1} onClick={() => setQty(qty - 1)}>−</button>
              <span aria-live="polite">{qty}</span>
              <button aria-label={t('increase')} disabled={qty === 20} onClick={() => setQty(qty + 1)}>+</button>
            </div>
            <button
              className="btn btn-primary" disabled={!meal.available}
              onClick={() => { if (addToCart(meal.id, qty)) (document.querySelector('dialog.meal-dialog') as HTMLDialogElement | null)?.close(); }}
            >
              {meal.available ? t('addOrder', { n: qty, total: formatMoney(total, lang) }) : t('soldOut')}
            </button>
          </div>
        </aside>
      </div>
    </Dialog>
  );
}
