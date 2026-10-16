// Turn a draft review into the deck builder's pool.

import type { DraftReview } from '$lib/api/types';
import type { PoolCard } from './model';

/**
 * Every card the drafter took, in pick order, minus any basic lands: the
 * builder's own buttons add those (ADR 0025 s1), and the server prunes them
 * from the pool too.
 */
export function poolFromReview(review: DraftReview): PoolCard[] {
	const pool: PoolCard[] = [];
	review.analysis.picks.forEach((pick, i) => {
		const info = review.cards[pick.picked];
		if (!info || info.type_line.startsWith('Basic Land')) return;
		pool.push({
			key: `p${i}`, // the pick's position: unique even for a second copy of a card
			id: pick.picked,
			name: info.name,
			cmc: info.cmc,
			image: info.image_normal
		});
	});
	return pool;
}
