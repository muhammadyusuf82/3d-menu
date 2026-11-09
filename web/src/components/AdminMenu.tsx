import { useState } from 'react';
import type { Category, Container, Ingredient, Meal, ModelKind, Shape } from '../../../shared/types.ts';
import { api, fileToDataUrl } from '../lib/api.ts';
import { formatMoney, loc } from '../lib/menu.ts';
import { useApp } from '../store.tsx';
import { Dialog } from './common.tsx';

const SHAPES: Shape[] = ['disc', 'slab', 'mound', 'scatter', 'rings', 'drizzle', 'sphere', 'roll', 'tall', 'liquid', 'foam', 'ice', 'leaf'];
const CONTAINERS: Container[] = ['plate', 'board', 'bowl', 'glass', 'mug', 'cup', 'none'];
const hex4 = () => Math.floor(Math.random() * 65536).toString(16).padStart(4, '0');

export function MenuManager() {
  const { snap, t, lang, toast, errorText, refresh, catsById } = useApp();
  const [catFilter, setCatFilter] = useState('all');
  const [q, setQ] = useState('');
  const [editMeal, setEditMeal] = useState<Partial<Meal> | null>(null);
  const [editCat, setEditCat] = useState<Partial<Category> | null>(null);

  const cats = [...(snap?.categories ?? [])].sort((a, b) => a.sort - b.sort);
  const ordered = [...cats.filter((c) => !c.parentId).flatMap((p) => [p, ...cats.filter((c) => c.parentId === p.id)])];
  const meals = (snap?.meals ?? []).filter((m) => {
    if (catFilter !== 'all' && m.categoryId !== catFilter && catsById.get(m.categoryId)?.parentId !== catFilter) return false;
    const n = q.trim().toLowerCase();
    return !n || (m.name[0] + ' ' + m.name[1]).toLowerCase().includes(n);
  });

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    try { await fn(); if (ok) toast(ok, 'ok'); await refresh(); return true; } catch (e) { toast(errorText(e), 'error'); await refresh(); return false; }
  };

  return (
    <>
      <section className="block">
        <div className="block-head">
          <h3>{t('categoriesTitle')}</h3>
          <button className="btn btn-primary" onClick={() => setEditCat({})}>＋ {t('newCategory')}</button>
        </div>
        <div className="cat-list">
          {ordered.map((c) => (
            <div className={'cat-row' + (c.parentId ? ' sub' : '')} key={c.id}>
              <span>{c.parentId ? '↳ ' : ''}{c.icon} <b>{loc(c.name, lang)}</b> <small className="muted">({(snap?.meals ?? []).filter((m) => m.categoryId === c.id).length})</small></span>
              <span className="order-actions">
                <button className="btn btn-sm" onClick={() => setEditCat(c)}>{t('edit')}</button>
                <button className="btn btn-sm btn-ghost-danger" onClick={() => {
                  if (window.confirm(t('confirmDeleteCategory', { name: loc(c.name, lang) }))) void run(() => api.deleteCategory(c.id), t('deleted'));
                }}>{t('delete')}</button>
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="block">
        <div className="block-head">
          <h3>{t('mealsTitle')}</h3>
          <button className="btn btn-primary" onClick={() => setEditMeal({})}>＋ {t('newMeal')}</button>
        </div>
        <div className="list-tools">
          <select value={catFilter} onChange={(e) => setCatFilter(e.target.value)} aria-label={t('categories')}>
            <option value="all">{t('All')}</option>
            {ordered.map((c) => <option key={c.id} value={c.id}>{c.parentId ? '— ' : ''}{loc(c.name, lang)}</option>)}
          </select>
          <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('search')} aria-label={t('search')} />
        </div>
        <div className="meal-admin">
          {meals.map((m) => (
            <div className="admin-menu-row" key={m.id}>
              <span className="am-icon" aria-hidden="true">{catsById.get(m.categoryId)?.icon ?? '🍽️'}</span>
              <span className="am-name">{loc(m.name, lang)}<small className="muted"> · {loc(catsById.get(m.categoryId)?.name ?? ['', ''], lang)}</small></span>
              <PriceInput meal={m} onCommit={(price) => run(() => api.patchMeal(m.id, { price }), t('priceUpdated', { total: formatMoney(price, lang) }))} />
              <button className="toggle" role="switch" aria-checked={m.available} aria-label={t('availability', { name: loc(m.name, lang) })}
                onClick={() => void run(() => api.patchMeal(m.id, { available: !m.available }))} />
              <button className="btn btn-sm" onClick={() => setEditMeal(m)}>{t('edit')}</button>
              <button className="btn btn-sm btn-ghost-danger" onClick={() => {
                if (window.confirm(t('confirmDeleteMeal', { name: loc(m.name, lang) }))) void run(() => api.deleteMeal(m.id), t('deleted'));
              }}>{t('delete')}</button>
            </div>
          ))}
          {meals.length === 0 && <div className="empty">{t('noMeals')}</div>}
        </div>
      </section>

      {editCat && <CategoryForm initial={editCat} onClose={() => setEditCat(null)} />}
      {editMeal && <MealForm initial={editMeal} onClose={() => setEditMeal(null)} />}
    </>
  );
}

function PriceInput({ meal, onCommit }: { meal: Meal; onCommit: (price: number) => Promise<boolean> }) {
  const { t, toast } = useApp();
  const [val, setVal] = useState<string | null>(null);
  const commit = async () => {
    if (val === null) return;
    const n = Number(val);
    if (!val.trim() || !Number.isFinite(n) || n < 0 || n > 100_000_000) { toast(t('invalidPrice'), 'error'); setVal(null); return; }
    if (Math.round(n) !== meal.price) await onCommit(Math.round(n));
    setVal(null);
  };
  return (
    <input type="number" min={0} step={500} inputMode="numeric" value={val ?? String(meal.price)} aria-label={t('priceFor', { name: meal.name[0] })}
      onChange={(e) => setVal(e.target.value)} onBlur={() => void commit()} onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
  );
}

function CategoryForm({ initial, onClose }: { initial: Partial<Category>; onClose: () => void }) {
  const { snap, t, lang, toast, errorText, refresh } = useApp();
  const [nameEn, setNameEn] = useState(initial.name?.[0] ?? '');
  const [nameUz, setNameUz] = useState(initial.name?.[1] ?? '');
  const [icon, setIcon] = useState(initial.icon ?? '🍽️');
  const [parentId, setParentId] = useState(initial.parentId ?? '');
  const [sort, setSort] = useState(String(initial.sort ?? 100));
  const [busy, setBusy] = useState(false);
  const hasChildren = (snap?.categories ?? []).some((c) => c.parentId === initial.id);
  const parents = (snap?.categories ?? []).filter((c) => !c.parentId && c.id !== initial.id);

  const save = async () => {
    setBusy(true);
    try {
      await api.saveCategory({ id: initial.id, name: [nameEn.trim(), nameUz.trim()], icon: icon.trim(), parentId: parentId || null, sort: Number(sort) });
      toast(t('saved'), 'ok'); await refresh(); onClose();
    } catch (e) { toast(errorText(e), 'error'); } finally { setBusy(false); }
  };
  return (
    <Dialog onClose={onClose} className="form-dialog narrow" label={t('newCategory')}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <h2>{initial.id ? t('editCategory') : t('newCategory')}</h2>
        <div className="grid2">
          <label className="field"><span>{t('nameEn')}</span><input required maxLength={60} value={nameEn} onChange={(e) => setNameEn(e.target.value)} /></label>
          <label className="field"><span>{t('nameUz')}</span><input maxLength={60} value={nameUz} onChange={(e) => setNameUz(e.target.value)} /></label>
        </div>
        <div className="grid3">
          <label className="field"><span>{t('icon')}</span><input maxLength={8} value={icon} onChange={(e) => setIcon(e.target.value)} /></label>
          <label className="field"><span>{t('parentCategory')}</span>
            <select value={parentId} onChange={(e) => setParentId(e.target.value)} disabled={hasChildren}>
              <option value="">{t('none')}</option>
              {parents.map((c) => <option key={c.id} value={c.id}>{loc(c.name, lang)}</option>)}
            </select>
          </label>
          <label className="field"><span>{t('sortOrder')}</span><input type="number" min={0} value={sort} onChange={(e) => setSort(e.target.value)} /></label>
        </div>
        <div className="receipt-actions">
          <button type="button" className="btn" onClick={() => (document.querySelector('dialog.form-dialog') as HTMLDialogElement | null)?.close()}>{t('cancel')}</button>
          <button className="btn btn-primary" disabled={busy || !nameEn.trim()}>{t('save')}</button>
        </div>
      </form>
    </Dialog>
  );
}

interface IngRow extends Omit<Ingredient, 'amount' | 'size'> { amount: string; size: string }

function MealForm({ initial, onClose }: { initial: Partial<Meal>; onClose: () => void }) {
  const { snap, t, lang, toast, errorText, refresh } = useApp();
  const cats = [...(snap?.categories ?? [])].sort((a, b) => a.sort - b.sort);
  const ordered = [...cats.filter((c) => !c.parentId).flatMap((p) => [p, ...cats.filter((c) => c.parentId === p.id)])];
  const [categoryId, setCategoryId] = useState(initial.categoryId ?? ordered.find((c) => !snap?.categories.some((x) => x.parentId === c.id))?.id ?? ordered[0]?.id ?? '');
  const [nameEn, setNameEn] = useState(initial.name?.[0] ?? '');
  const [nameUz, setNameUz] = useState(initial.name?.[1] ?? '');
  const [tagEn, setTagEn] = useState(initial.tag?.[0] ?? '');
  const [tagUz, setTagUz] = useState(initial.tag?.[1] ?? '');
  const [descEn, setDescEn] = useState(initial.desc?.[0] ?? '');
  const [descUz, setDescUz] = useState(initial.desc?.[1] ?? '');
  const [price, setPrice] = useState(String(initial.price ?? 50000));
  const [prep, setPrep] = useState(String(initial.prepMin ?? 10));
  const [kcal, setKcal] = useState(String(initial.kcal ?? 400));
  const [available, setAvailable] = useState(initial.available ?? true);
  const [photo, setPhoto] = useState<string | null>(initial.photo ?? null);
  const [kind] = useState<ModelKind>(initial.model?.kind ?? 'generic');
  const [container, setContainer] = useState<Container>(initial.model?.container ?? 'plate');
  const [spread, setSpread] = useState(initial.model?.arrange === 'spread');
  const [rows, setRows] = useState<IngRow[]>(() => (initial.ingredients?.length
    ? initial.ingredients.map((i) => ({ ...i, amount: String(i.amount), size: i.size ? String(i.size) : '' }))
    : [{ id: 'ing-' + hex4(), name: ['', ''], amount: '100', unit: 'g', color: '#c98a45', shape: 'mound', size: '' }]));
  const [busy, setBusy] = useState(false);

  const setRow = (i: number, patch: Partial<IngRow>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const move = (i: number, d: number) => setRows((r) => {
    const j = i + d;
    if (j < 0 || j >= r.length) return r;
    const c = [...r];
    [c[i], c[j]] = [c[j], c[i]];
    return c;
  });

  const upload = async (file: File | undefined) => {
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) { toast(t('imageTypeError'), 'error'); return; }
    if (file.size > 3 * 1024 * 1024) { toast(t('imageSizeError'), 'error'); return; }
    try { setPhoto((await api.upload(await fileToDataUrl(file))).path); } catch (e) { toast(errorText(e), 'error'); }
  };

  const save = async () => {
    setBusy(true);
    try {
      const ingredients = rows.map((r) => ({
        id: r.id, name: [r.name[0].trim(), r.name[1].trim()] as [string, string], amount: Number(r.amount), unit: r.unit, color: r.color,
        ...(r.shape ? { shape: r.shape } : {}), ...(r.size ? { size: Number(r.size) } : {}),
      }));
      await api.saveMeal({
        id: initial.id, categoryId, name: [nameEn.trim(), nameUz.trim()], tag: [tagEn.trim(), tagUz.trim()], desc: [descEn.trim(), descUz.trim()],
        price: Number(price), prepMin: Number(prep), kcal: Number(kcal), available, photo, ingredients,
        model: { kind, container, ...(spread ? { arrange: 'spread' as const } : {}) },
      });
      toast(t('saved'), 'ok'); await refresh(); onClose();
    } catch (e) { toast(errorText(e), 'error'); } finally { setBusy(false); }
  };

  const legacy = kind !== 'generic';
  return (
    <Dialog onClose={onClose} className="form-dialog wide" label={t('newMeal')}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <h2>{initial.id ? t('editMeal') : t('newMeal')}</h2>
        <div className="grid2">
          <label className="field"><span>{t('nameEn')}</span><input required maxLength={80} value={nameEn} onChange={(e) => setNameEn(e.target.value)} /></label>
          <label className="field"><span>{t('nameUz')}</span><input maxLength={80} value={nameUz} onChange={(e) => setNameUz(e.target.value)} /></label>
          <label className="field"><span>{t('tagEn')}</span><input maxLength={120} value={tagEn} onChange={(e) => setTagEn(e.target.value)} /></label>
          <label className="field"><span>{t('tagUz')}</span><input maxLength={120} value={tagUz} onChange={(e) => setTagUz(e.target.value)} /></label>
          <label className="field"><span>{t('descEn')}</span><textarea rows={3} maxLength={600} value={descEn} onChange={(e) => setDescEn(e.target.value)} /></label>
          <label className="field"><span>{t('descUz')}</span><textarea rows={3} maxLength={600} value={descUz} onChange={(e) => setDescUz(e.target.value)} /></label>
        </div>
        <div className="grid4">
          <label className="field"><span>{t('category')}</span>
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              {ordered.map((c) => <option key={c.id} value={c.id}>{c.parentId ? '— ' : ''}{loc(c.name, lang)}</option>)}
            </select>
          </label>
          <label className="field"><span>{t('priceUzs')}</span><input type="number" min={0} step={500} required value={price} onChange={(e) => setPrice(e.target.value)} /></label>
          <label className="field"><span>{t('prepTime')} ({t('min')})</span><input type="number" min={0} value={prep} onChange={(e) => setPrep(e.target.value)} /></label>
          <label className="field"><span>{t('energy')} ({t('kcal')})</span><input type="number" min={0} value={kcal} onChange={(e) => setKcal(e.target.value)} /></label>
        </div>
        <div className="grid3">
          <label className="field"><span>{t('container')}</span>
            <select value={container} onChange={(e) => setContainer(e.target.value as Container)} disabled={legacy}>
              {CONTAINERS.map((c) => <option key={c} value={c}>{t('container_' + c)}</option>)}
            </select>
          </label>
          <div className="field">
            <span>{t('photo')}</span>
            <div className="upload-row">
              {photo && <img className="event-thumb" src={photo} alt="" />}
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ''; }} />
              {photo && <button type="button" className="btn btn-sm" onClick={() => setPhoto(null)}>{t('removeImage')}</button>}
            </div>
          </div>
          <label className="check-inline"><input type="checkbox" checked={available} onChange={(e) => setAvailable(e.target.checked)} /> {t('available')}</label>
        </div>

        <fieldset className="fs">
          <legend>{t('ingredientsTitle')}</legend>
          <p className="muted small">{legacy ? t('legacyModelNote') : t('ingredientsHelp')}</p>
          {!legacy && <label className="check-inline"><input type="checkbox" checked={spread} onChange={(e) => setSpread(e.target.checked)} /> {t('arrangeSpread')}</label>}
          {rows.map((r, i) => (
            <div className="ing-row" key={r.id}>
              <input placeholder={t('nameEn')} required value={r.name[0]} onChange={(e) => setRow(i, { name: [e.target.value, r.name[1]] })} aria-label={t('nameEn')} />
              <input placeholder={t('nameUz')} value={r.name[1]} onChange={(e) => setRow(i, { name: [r.name[0], e.target.value] })} aria-label={t('nameUz')} />
              <input type="number" min={0} className="num" value={r.amount} onChange={(e) => setRow(i, { amount: e.target.value })} aria-label={t('amount')} />
              <select value={r.unit} onChange={(e) => setRow(i, { unit: e.target.value as Ingredient['unit'] })} aria-label={t('unit')}>
                {(['g', 'ml', 'pcs', 'slices'] as const).map((u) => <option key={u} value={u}>{u === 'g' ? t('unit_g') : u === 'ml' ? t('unit_ml') : t(u)}</option>)}
              </select>
              <input type="color" value={r.color} onChange={(e) => setRow(i, { color: e.target.value })} aria-label={t('color')} />
              {!legacy && (
                <>
                  <select value={r.shape ?? ''} onChange={(e) => setRow(i, { shape: (e.target.value || undefined) as Shape | undefined })} aria-label={t('shape')}>
                    <option value="">{t('shape_scatter')}</option>
                    {SHAPES.map((s) => <option key={s} value={s}>{t('shape_' + s)}</option>)}
                  </select>
                  <input type="number" step={0.1} min={0.1} max={3} className="num" placeholder="1" value={r.size} onChange={(e) => setRow(i, { size: e.target.value })} aria-label={t('size')} />
                </>
              )}
              <span className="row-actions">
                <button type="button" className="btn btn-sm" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t('moveUp')}>↑</button>
                <button type="button" className="btn btn-sm" disabled={i === rows.length - 1} onClick={() => move(i, 1)} aria-label={t('moveDown')}>↓</button>
                <button type="button" className="btn btn-sm btn-ghost-danger" disabled={rows.length === 1} onClick={() => setRows((x) => x.filter((_, j) => j !== i))} aria-label={t('delete')}>✕</button>
              </span>
            </div>
          ))}
          {!legacy && <button type="button" className="btn btn-sm" onClick={() => setRows((r) => [...r, { id: 'ing-' + hex4(), name: ['', ''], amount: '50', unit: 'g', color: '#c98a45', shape: 'scatter', size: '' }])}>＋ {t('addIngredient')}</button>}
        </fieldset>

        <div className="receipt-actions">
          <button type="button" className="btn" onClick={() => (document.querySelector('dialog.form-dialog') as HTMLDialogElement | null)?.close()}>{t('cancel')}</button>
          <button className="btn btn-primary" disabled={busy || !nameEn.trim() || !categoryId}>{busy ? t('sending') : t('save')}</button>
        </div>
      </form>
    </Dialog>
  );
}
