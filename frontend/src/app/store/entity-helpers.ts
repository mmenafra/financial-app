import { createEntityAdapter, EntityState } from '@ngrx/entity';

/**
 * Example of `@ngrx/entity` — replace with your domain model and feature key.
 * Import adapters from a feature `*.reducer.ts` when you add collection slices.
 */
export interface WithId {
  id: string;
}

export type PlaceholderEntityState = EntityState<WithId> & { loading: boolean };

export const withIdAdapter = createEntityAdapter<WithId>();
