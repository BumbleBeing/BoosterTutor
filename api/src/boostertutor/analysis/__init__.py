"""Pure analysis: no network, no database, no clock.

Everything in here takes plain Python values and returns plain Python values,
so it can be tested exhaustively on tiny hand-built inputs. Database reads
happen in the caller and are handed in as plain values.
"""
