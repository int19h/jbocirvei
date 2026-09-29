> **Status 2026-09-14.** We received the Lensisku, jbovlaste and Tiki exports on 2026-09-13. They are kept in the local archive tier. We removed the per-user tables and `tiki_forums` locally, so there is no need to export them again. **We still need the MediaWiki export (§2).**

# Database export request — for the lojban.org server operator

Purpose: jbomo'i (`https://github.com/int19h/jbomohi`) publishes the **public** record of the Lojban community again, as a git repository. Each commit is one event from a source, such as a wiki revision, a change to a definition, or a comment.

- Everything that the sites show to the public goes in.
- Everything else must never leave your machine. This means passwords, e-mail addresses, tokens, sessions, private messages, payments, IP addresses, content that is not published or is still waiting in a queue, notes that belong to one user, and the rows that show how each person voted.

The commands below split the data in exactly this way. The file `doc/research/dump-schemas.md` in the repository gives the details, and the reason for each table. It was checked against the source code of jbovlaste, Lensisku, MediaWiki 1.38 and Tiki.

We need three databases, with one dump of each, compressed with gzip. We do not need checksums. The sizes are about: tens of MB for Lensisku/jbovlaste, a few hundred MB for MediaWiki (most of it is the `text` table), and tens of MB for Tiki. You can send the files in any way, for example a URL behind HTTP auth, or scp. We use the files only on our own machine. We never put them into git and never upload them to CI.

---

## 1. Lensisku (this is also the jbovlaste data)

The PostgreSQL database of Lensisku (`lojban_lens`) *is* the jbovlaste database. It was migrated in place, and it has the same `users`, `valsi`, `definitions`, `comments` and `definitionvotes` tables, with the same ids. So one dump covers both.

There may also be a separate, frozen jbovlaste database (a `jbovlaste` database that is not `lojban_lens`). If there is, please dump it in the same way (§1b). It is the only place where the data from before the migration could be different. If `lojban_lens` is the only database, skip §1b.

```sh
DB=lojban_lens   # the Lensisku database (contains the migrated jbovlaste tables)

# a) everything except the tables that hold private data
pg_dump -Fp --no-owner --no-privileges --exclude-table-data='*' --schema-only "$DB" > lensisku-schema.sql
pg_dump -Fp --no-owner --no-privileges --data-only \
  -T users -T users_view -T definitionvotes -T natlangwordvotes \
  -T user_sessions -T user_session_events -T password_reset_requests -T password_change_verifications \
  -T oauth_accounts -T private_messages -T message_threads -T thread_participants -T user_message_blocks \
  -T message_encryption_keys -T message_notifications -T webrtc_signaling \
  -T payments -T balance_transactions -T paypal_subscriptions -T payment_audit_log -T user_balances \
  -T user_search_history -T assistant_chats -T user_notifications -T user_settings -T user_profile_images \
  -T valsi_subscriptions -T follows -T comment_bookmarks -T comment_opinion_votes -T comment_reactions \
  -T flashcards -T flashcard_levels -T flashcard_level_items -T flashcard_quiz_options -T flashcard_review_history \
  -T user_flashcard_progress -T user_level_progress -T user_quiz_answer_history -T level_prerequisites \
  -T collections -T collection_items -T collection_images -T collection_item_images -T collection_item_sounds \
  -T cached_dictionary_exports -T wiki_articles -T wiki_sync_state \
  "$DB" > lensisku-public-data.sql

# b) the public columns of users, as data only (no password, no email, no tokens, no votesize)
psql "$DB" -c "\copy (SELECT userid, username, realname, url, personal, created_at, role, disabled FROM users) TO 'lensisku-users-public.csv' CSV HEADER"

# c) vote totals only — voter identity is not public in either application
psql "$DB" -c "\copy (SELECT definitionid, valsiid, langid, SUM(value) AS score, COUNT(*) AS votes, MAX(time) AS last_vote_time FROM definitionvotes GROUP BY definitionid, valsiid, langid) TO 'lensisku-definition-scores.csv' CSV HEADER"

gzip lensisku-schema.sql lensisku-public-data.sql
```

We built the list of excluded tables from two places: the source schema, and the export of 2026-09-13. The list leaves out:

- everything that belongs to one user: chats with the AI assistant of the site, notifications, settings, avatars, balances, subscriptions, follows, bookmarks, reactions, progress in flashcards and quizzes, and collections (private ones too);
- `users_view`, because it shows the private `votesize`;
- caches;
- the copy of the MediaWiki wiki, because we take the wiki from MediaWiki itself.

If a table in the list does not exist in your version, remove its `-T`. Please do not remove the `-T` for a table that does exist: leaving it out is safe only when the table is not there. If you think other tables are private, exclude them too, and tell us their names.

### 1b. A separate jbovlaste database, if one still exists

```sh
DB=jbovlaste
pg_dump -Fp --no-owner --no-privileges -T users -T users_view -T definitionvotes -T natlangwordvotes "$DB" | gzip > jbovlaste-public.sql.gz
psql "$DB" -c "\copy (SELECT userid, username, realname, url, personal FROM users) TO 'jbovlaste-users-public.csv' CSV HEADER"
psql "$DB" -c "\copy (SELECT definitionid, valsiid, langid, SUM(value) AS score, COUNT(*) AS votes, MAX(time) AS last_vote_time FROM definitionvotes GROUP BY definitionid, valsiid, langid) TO 'jbovlaste-definition-scores.csv' CSV HEADER"
```

---

## 2. MediaWiki (mw.lojban.org, 1.38.7 / MariaDB)

`mysqldump` cannot choose columns. So we export the `user` table on its own, with only its public columns.

```sh
DB=my_wiki   # adjust
MYSQLDUMP="mysqldump --single-transaction --quick --no-tablespaces \
  --default-character-set=binary --hex-blob --skip-extended-insert"

# a) everything needed to reconstruct every revision of every page
$MYSQLDUMP $DB \
  page revision revision_actor_temp revision_comment_temp \
  slots slot_roles content content_models text comment actor \
  archive logging log_search page_props redirect page_restrictions \
  image oldimage change_tag change_tag_def category categorylinks \
  interwiki site_stats | gzip > wiki-content.sql.gz

# b) the user table, public columns only
mysql --batch --raw $DB -e \
  "SELECT user_id, user_name, user_real_name, user_registration, user_editcount FROM user" \
  | gzip > wiki-users.tsv.gz

# c) only if $wgDefaultExternalStore is set in LocalSettings.php: the external-store cluster(s)
# $MYSQLDUMP <cluster_db> blobs | gzip > wiki-es-cluster1.sql.gz

```

You must use `--hex-blob` and `--default-character-set=binary`. The column `text.old_text` holds compressed binary data, and its bytes must not be converted to another character set.

We do **not** want these tables, on purpose: `user_properties`, `user_former_groups`, `bot_passwords`, `ipblocks*`, `watchlist*`, `user_newtalk`, `recentchanges`, `ip_changes`, `filearchive`, `uploadstash`, `objectcache`, `cu_*`. We also do not want any `user` column other than the five above.

Two notes:

- We ask for `archive` (the deleted revisions) because history that was deleted and then restored matters. You may leave it out if you prefer.
- Our importer hides revisions that have `rev_deleted` bits set. The dump does not hide them, so the dump contains them as plain text. Handle the file with care because of this.

---

## 3. Tiki (tiki.lojban.org, the pre-2013 wiki)

The Tiki tables say they are `latin1`, but they hold UTF-8 bytes. Also, `tiki_history.data` is a blob, while `tiki_pages.data` is text. So you must use the character-set flags below. Without them, the bytes of the current version of a page will not match the bytes of the same version in its history.

```sh
DB=tiki   # adjust
MYSQLDUMP="mysqldump --single-transaction --quick --no-tablespaces \
  --default-character-set=latin1 --skip-set-charset --hex-blob --skip-extended-insert"

# a) pages, history, forums/comments, action log, categories, links
$MYSQLDUMP $DB \
  tiki_pages tiki_history tiki_comments tiki_actionlog \
  tiki_categories tiki_category_objects tiki_links tiki_wiki_attachments \
  tiki_pages_translation_bits tiki_translated_objects \
  | gzip > tiki-content.sql.gz
# (drop any table that does not exist in your Tiki version)

# NOT tiki_forums: it holds forum_password and a PLAINTEXT inbound_pop_password.
# Export only its public columns instead:
mysql --batch --raw $DB -e \
  "SELECT forumId, name, description, created, lastPost, comments, threads, moderator, section FROM tiki_forums" \
  | gzip > tiki-forums.tsv.gz

# b) users: login only, plus the public preference rows (real name, "information public/private")
mysql --batch --raw $DB -e "SELECT userId, login FROM users_users" | gzip > tiki-users.tsv.gz
mysql --batch --raw $DB -e \
  "SELECT user, prefName, value FROM tiki_user_preferences WHERE prefName IN ('realName','user_information','email is public')" \
  | gzip > tiki-user-preferences.tsv.gz

```

We do **not** want these, on purpose:

- any other `users_users` column (`password`, `provpass`, `hash`, `challenge`, `valid`, `email`, login times, avatars);
- the whole `tiki_forums` table (see above: `mysqldump` cannot leave out its password columns);
- `tiki_page_footnotes` (private notes of each user);
- `tiki_comments_queue` and `tiki_forums_queue` (posts that were never published);
- `tiki_semaphores`, the session and login tables, galleries, and file blobs.

Some of the tables we ask for have IP columns: `tiki_pages.ip`, `tiki_history.ip`, `tiki_comments.user_ip` and `tiki_actionlog.ip`. If you can, please empty them before the dump (run `UPDATE … SET ip=''` on a copy). If you cannot, our importer throws them away, and they never go into the repository.

---

## 4. Nothing else is needed from the server

We get the other data from public places:

- the mailing lists from the public `mail.lojban.org/lists-plain/*.maildir.zip` files and the MHonArc pages;
- the IRC logs from `lojban.org/irclogs/`;
- new wiki changes from the wiki API;
- new dictionary changes from the public `/api/jbovlaste/changes` feed of Lensisku.

If the `lists-plain` zip files are made again on a schedule, it would help us to know how often. If `llg-members` or `llg-board` ever become public, we will pick up their `lists-plain` directories without any extra work.
