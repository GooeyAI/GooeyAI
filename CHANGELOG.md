# 29-September-2026

**Added**

[Quote the interrupting message when a streamed WhatsApp reply is replaced](https://github.com/GooeyAI/gooey-server/commit/95fec8e9)
[Swipe the eco cost sheet down to close it](https://github.com/GooeyAI/gooey-server/commit/b270481e)

**Fixed**

[Add a fallback request method for status code 405 in the `_get_media_mimetype` function](https://github.com/GooeyAI/gooey-server/commit/e2d71530)
[Harden the eco sheet swipe against interrupts and motion settings](https://github.com/GooeyAI/gooey-server/commit/6da1f804)
[Centre the eco cost modal vertically on desktop](https://github.com/GooeyAI/gooey-server/commit/0ae4ec96)
[Print full traceback for eco cost failures](https://github.com/GooeyAI/gooey-server/commit/738aa745)
[Capture eco cost failures in Sentry](https://github.com/GooeyAI/gooey-server/commit/b3ed12bc)

# 28-September-2026

**Fixed**

[Fix the publish dot on the top bar](https://github.com/GooeyAI/gooey-server/commit/5c140a92)
[Let the Ask Gooey button wear the mark or nothing at all](https://github.com/GooeyAI/gooey-server/commit/a8eed0e4)

# 25-September-2026

**Added**

[Show usage in USD instead of credits](https://github.com/GooeyAI/gooey-server/commit/2ee0d0da)
[Custom hover band, tooltip and legend for the usage chart](https://github.com/GooeyAI/gooey-server/commit/e428fe77)
[/account/usage page with monthly credit usage by recipe](https://github.com/GooeyAI/gooey-server/commit/90339521)

# 24-September-2026

**Added**

[Read the turns slider as monthly users at 8 messages a month](https://github.com/GooeyAI/gooey-server/commit/ae761ba9)
[Per-run eco cost in the top bar and a cost & environment impact modal](https://github.com/GooeyAI/gooey-server/commit/3869056f)
[Let sliders be empty and unset optional model fields](https://github.com/GooeyAI/gooey-server/commit/d42a3e89)
[Add erase button to image/video model sliders](https://github.com/GooeyAI/gooey-server/commit/dee0875f)
[Enable fullscreen preview dialog for generated images](https://github.com/GooeyAI/gooey-server/commit/6e220460)
[Add schema-driven image generation](https://github.com/GooeyAI/gooey-server/commit/b26cc567)

**Fixed**

[Never let an eco cost failure break the page](https://github.com/GooeyAI/gooey-server/commit/b43603bc)
[Explain low confidence with ecocost's reason codes](https://github.com/GooeyAI/gooey-server/commit/6985875d)
[Review fixes, mobile access, and a stable phone layout](https://github.com/GooeyAI/gooey-server/commit/cfb17999)
[Keep workflows saved after login private](https://github.com/GooeyAI/gooey-server/commit/34fef273)
[Keep Bot Builder workflow copies private](https://github.com/GooeyAI/gooey-server/commit/bb6a8898)
[Keep duplicated workflows private](https://github.com/GooeyAI/gooey-server/commit/932df1ea)
[Stop the two side tracks insisting on being the same width](https://github.com/GooeyAI/gooey-server/commit/02af5322)
[Measure what the bar wants, not what it was already squeezed into](https://github.com/GooeyAI/gooey-server/commit/1ce3dd16)
[Fall back to the workflow's name when no wordmark is sent](https://github.com/GooeyAI/gooey-server/commit/fb77c1eb)
[Run safety checker on the rendered prompt](https://github.com/GooeyAI/gooey-server/commit/a0bfcd74)
[Renumber image generation migrations for master](https://github.com/GooeyAI/gooey-server/commit/969af49a)
[Hide outputs from unselected image models](https://github.com/GooeyAI/gooey-server/commit/e994d7d9)
[Render image size enums as selectors](https://github.com/GooeyAI/gooey-server/commit/6388e8b2)
[Accept empty image generation examples](https://github.com/GooeyAI/gooey-server/commit/88ee70d6)

# 23-September-2026

**Added**

[Use datetime + workflow title filenames for all VideoGenPage videos](https://github.com/GooeyAI/gooey-server/commit/ea007c60)
[Name agent-generated videos with a UTC timestamp and agent title](https://github.com/GooeyAI/gooey-server/commit/63a5bcbd)
[Allow overriding the filename of re-uploaded fal assets](https://github.com/GooeyAI/gooey-server/commit/7ad349f4)

**Fixed**

[Keep the file extension when a fal filename stem contains a dot](https://github.com/GooeyAI/gooey-server/commit/afcf18dc)

# 22-September-2026

**Fixed**

[Deferred pane shouldn't load after its switched away from](https://github.com/GooeyAI/gooey-server/commit/8ca902da)

# 21-September-2026

**Added**

[Shed the bar's labels by measuring, not by breakpoint](https://github.com/GooeyAI/gooey-server/commit/147a32f8)

**Fixed**

[Make the fully-labelled bar prove it has room for one more chip](https://github.com/GooeyAI/gooey-server/commit/ae1a664a)
[Pair the view-transition name to the transitioning instance, not a startup counter](https://github.com/GooeyAI/gooey-server/commit/78257b49)
[Stop a tooltip outliving the control it points at](https://github.com/GooeyAI/gooey-server/commit/85e3853b)

# 19-September-2026

**Added**

[Hold tooltips back 1.2s](https://github.com/GooeyAI/gooey-server/commit/d44ef37f)
[Name the bar's controls with the tooltip v2 uses elsewhere](https://github.com/GooeyAI/gooey-server/commit/fae56663)

**Fixed**

[Let a tooltip out of the box that laid out the thing it points at](https://github.com/GooeyAI/gooey-server/commit/d65ae2c8)
[Gate the bar's labels on a 1440px window, not 1512](https://github.com/GooeyAI/gooey-server/commit/6e6a4578)
[Collapse the bar's labels before its controls overlap](https://github.com/GooeyAI/gooey-server/commit/97168b5e)
[Lighten the header rule and give it room](https://github.com/GooeyAI/gooey-server/commit/e9d8617d)
[Rule the header, not the whole bar](https://github.com/GooeyAI/gooey-server/commit/35666ad2)
[Stop Duplicate and the publish control sharing one label](https://github.com/GooeyAI/gooey-server/commit/74fb22e9)
[Give New Chat and the way back to a published run a home again](https://github.com/GooeyAI/gooey-server/commit/0a7f95cf)
[Do not offer Close Preview where it would leave no tab selected](https://github.com/GooeyAI/gooey-server/commit/09f26c8c)
[The mobile header's wordmark, title width and Ask Gooey mark](https://github.com/GooeyAI/gooey-server/commit/192bac1e)

# 18-September-2026

**Added**

[Match the mobile header and tab strip to the Figma flow](https://github.com/GooeyAI/gooey-server/commit/e625a2b2)

**Fixed**

[Bound upload metadata filenames](https://github.com/GooeyAI/gooey-server/commit/1be0c076)

# 17-September-2026

**Fixed**

[Keep translated raw_tts_text when it matches output_text](https://github.com/GooeyAI/gooey-server/commit/f209b656)
[Clear stale raw_tts_text between streamed chunks](https://github.com/GooeyAI/gooey-server/commit/d13a18cb)

# 16-September-2026

**Added**

[Shimmer loading indicator, fix its SSR readiness race](https://github.com/GooeyAI/gooey-server/commit/ad499e3d)
[Use previewImg as a blurred loading placeholder for expandable video](https://github.com/GooeyAI/gooey-server/commit/8a978fe0)
[Run metadata in the v2 debug pane](https://github.com/GooeyAI/gooey-server/commit/7ddfb727)

**Fixed**

[Letter spacings](https://github.com/GooeyAI/gooey-server/commit/ea4e4aab)
[Open About's meta cards in the split, not the editor alone](https://github.com/GooeyAI/gooey-server/commit/1419beed)
[Let a picked view outrank the run reveal, so Usage to Edit lands on Edit](https://github.com/GooeyAI/gooey-server/commit/7394df8f)
[Underline only on hover](https://github.com/GooeyAI/gooey-server/commit/5f4b3365)
[Keep the view you pick when leaving Usage](https://github.com/GooeyAI/gooey-server/commit/5b431745)

# 15-September-2026

**Added**

[Forward trailing text after extension number to the bot](https://github.com/GooeyAI/gooey-server/commit/2b5dfff4)
[Give a logged out visitor the browser's own share sheet on About](https://github.com/GooeyAI/gooey-server/commit/1f37b785)
[Close the About surface with Privacy, Terms and a Report form](https://github.com/GooeyAI/gooey-server/commit/4c5e2c54)
[Animate the thumbnail-to-lightbox transition with View Transitions](https://github.com/GooeyAI/gooey-server/commit/e80da998)
[Run metadata in the v2 debug pane (initial)](https://github.com/GooeyAI/gooey-server/commit/d83fdd6a)
[Custom play/pause/mute overlay for inline video, fix dialog action bar overlap](https://github.com/GooeyAI/gooey-server/commit/a96e7ea0)

**Fixed**

[Two layout regressions and a video-open transition snap](https://github.com/GooeyAI/gooey-server/commit/6f6e83ea)
[Sever window.opener before navigating the download fallback window](https://github.com/GooeyAI/gooey-server/commit/1222579d)
[Unique per-instance view-transition-name, reorder helpers](https://github.com/GooeyAI/gooey-server/commit/6dfdc151)
[Drop the /usage/ endpoint expectation from the v1 layout tests](https://github.com/GooeyAI/gooey-server/commit/d34a3e1d)
[Flag workflow dialog icon](https://github.com/GooeyAI/gooey-server/commit/300eca76)
[Stop the Debug pane demanding a workspace, which 500'd every public page](https://github.com/GooeyAI/gooey-server/commit/4d8b513c)
[Give the Builder's panel one key, from one place](https://github.com/GooeyAI/gooey-server/commit/15bb7bd4)
[Read the debug pane's author through current_sr_user](https://github.com/GooeyAI/gooey-server/commit/675d0322)
[Stop the Builder closing itself whenever the page it sits beside changes](https://github.com/GooeyAI/gooey-server/commit/a2c04d6c)
[Shrink the Debug pane's type on a phone](https://github.com/GooeyAI/gooey-server/commit/faf0f318)
[Offer the share url wherever there is no dialog, /agent/ included](https://github.com/GooeyAI/gooey-server/commit/416162ae)
[Give the page a real h1, and hang the About surface off it](https://github.com/GooeyAI/gooey-server/commit/8f66cb31)
[Keep the download fallback within Safari/iOS user activation](https://github.com/GooeyAI/gooey-server/commit/e7b6c29f)
[Move image expand button to top-left, matching video](https://github.com/GooeyAI/gooey-server/commit/867ad5bd)
[Media preview review findings from PR #1097](https://github.com/GooeyAI/gooey-server/commit/54874b10)
[Expand button fade grouping and icon direction](https://github.com/GooeyAI/gooey-server/commit/04817f79)
[Let the preview dialog backdrop reach the notch/Dynamic Island](https://github.com/GooeyAI/gooey-server/commit/1c641a8e)

# 14-September-2026

**Added**

[Add click-to-fullscreen preview for generated images/videos](https://github.com/GooeyAI/gooey-server/commit/83e1090d)

**Fixed**

[Suppress Safari's AirPlay icon overlapping the media expand button](https://github.com/GooeyAI/gooey-server/commit/105e20db)
[Trap and restore keyboard focus in media preview dialog](https://github.com/GooeyAI/gooey-server/commit/57cbde05)
[Prevent media preview expand buttons from submitting the form](https://github.com/GooeyAI/gooey-server/commit/514c6a3a)
[Stop a form post counting as arriving somewhere new, and resetting the view](https://github.com/GooeyAI/gooey-server/commit/defb29bb)

# 11-September-2026

**Added**

[Enhance chat widget with replay and accurate timestamping features](https://github.com/GooeyAI/gooey-server/commit/0aa1f318)
[Turn on showRunTime for /agent and the builder](https://github.com/GooeyAI/gooey-server/commit/05e156db)
[Add run time in the assistant message](https://github.com/GooeyAI/gooey-server/commit/8fff223b)
[Report how long the answer took on the response message](https://github.com/GooeyAI/gooey-server/commit/6d24c829)
[Enable editing controller-managed chat messages](https://github.com/GooeyAI/gooey-server/commit/3ba52b72)
[Rebuild the v2 mobile chrome on the new screens](https://github.com/GooeyAI/gooey-server/commit/8585e713)
[Extend the design system's type to the converted pages, and load it from CSS](https://github.com/GooeyAI/gooey-server/commit/9913d052)

**Fixed**

[Send created_at in the assistant entry too](https://github.com/GooeyAI/gooey-server/commit/5135ede3)
[Take Share out of the bar's publish control on a view-only page](https://github.com/GooeyAI/gooey-server/commit/e3178fe2)
[Stop the mobile crumb repeating the view pill](https://github.com/GooeyAI/gooey-server/commit/17a2a419)
[Centre the About switcher, and drop the header pill it duplicates](https://github.com/GooeyAI/gooey-server/commit/b8ddf904)
[Move the mobile switcher out of the header, and fix the swap that never fired](https://github.com/GooeyAI/gooey-server/commit/3ca462e5)
[Stop the mobile header showing the switcher twice](https://github.com/GooeyAI/gooey-server/commit/1d630e79)
[Bring the pane slide back, subtler, and stop a run laying out the wrong view first](https://github.com/GooeyAI/gooey-server/commit/59357d91)
[Drop the pane slide, which turned every transient layout into a visible round trip](https://github.com/GooeyAI/gooey-server/commit/5d18bb38)
[Scope the heading reset to the titles that need it, and give the editor its sizes back](https://github.com/GooeyAI/gooey-server/commit/4687425d)
[Let the About meta heading name only the kinds it holds](https://github.com/GooeyAI/gooey-server/commit/902d66a1)
[Put the Description heading back on About](https://github.com/GooeyAI/gooey-server/commit/5e0c8a2f)
[Drop the workflow card title to the design system's UI weight](https://github.com/GooeyAI/gooey-server/commit/3d6f1d9e)
[Reach the bold utilities, and give Ask Gooey's title the display face](https://github.com/GooeyAI/gooey-server/commit/dcd475a9)
[Give a card label three lines, and the card one height](https://github.com/GooeyAI/gooey-server/commit/296552f2)
[Lay the About cards out on a grid, six to a row](https://github.com/GooeyAI/gooey-server/commit/6176e0c5)
[Hold the About surface to the design's type and card size](https://github.com/GooeyAI/gooey-server/commit/595d40ee)
[Keep the view a run was started from, instead of imposing the work view](https://github.com/GooeyAI/gooey-server/commit/a94f9a19)

# 10-September-2026

**Added**

[Put the v2 surfaces on the design system's own typefaces](https://github.com/GooeyAI/gooey-server/commit/21a1cf2f)

**Fixed**

[Stop the sidebar forcing the split on every workflow it opens](https://github.com/GooeyAI/gooey-server/commit/cac0ae08)
[Settle three details of the v2 chrome](https://github.com/GooeyAI/gooey-server/commit/8c3158da)
[Keep the page-load bar out of the app talking to itself](https://github.com/GooeyAI/gooey-server/commit/8649234d)
[Take the v2 workspace's width off Bootstrap's container](https://github.com/GooeyAI/gooey-server/commit/04deb60d)
[Open a published run on About, a saved run on the work view, and drop the editor's dotted ring](https://github.com/GooeyAI/gooey-server/commit/e2bfc238)
[Let the instruction editor own its scroll, and open every workspace on About](https://github.com/GooeyAI/gooey-server/commit/5a6bee05)
[Correct the top bar's gates on a root recipe and a view-only page](https://github.com/GooeyAI/gooey-server/commit/1134b80d)
[Give layout v2 a heading outline a crawler can read](https://github.com/GooeyAI/gooey-server/commit/75fc9176)
[Ignore avoid repetition for all runs](https://github.com/GooeyAI/gooey-server/commit/346a2690)
[Upgrade Azure Speech SDK for CRL compatibility](https://github.com/GooeyAI/gooey-server/commit/8403e9ad)
[Authorize builder runs before submission](https://github.com/GooeyAI/gooey-server/commit/28505d05)
[Stop the insufficient-credits card from scrolling](https://github.com/GooeyAI/gooey-server/commit/1e98d829)
[Rerun insufficient-credit workflows in fallback workspace](https://github.com/GooeyAI/gooey-server/commit/2b0bc2dc)
[Handle insufficient credits in builder](https://github.com/GooeyAI/gooey-server/commit/95b84991)

# 09-September-2026

**Added**

[Add GPT Image Sunburst and Flare](https://github.com/GooeyAI/gooey-server/commit/8e45aedc)

**Fixed**

[Send the Examples tab to explore from a published run too](https://github.com/GooeyAI/gooey-server/commit/4202b6f7)
[Keep a shared example link pointing at the run it named](https://github.com/GooeyAI/gooey-server/commit/2bf17b75)
[Let a keyboard close the top bar's menus, and stop the shell re-rendering everything](https://github.com/GooeyAI/gooey-server/commit/03f90f03)
[Correct GPT Image 2.5 token pricing](https://github.com/GooeyAI/gooey-server/commit/9878a226)
[Use GPT Image 2.5 model identifiers and labels](https://github.com/GooeyAI/gooey-server/commit/6f19eb37)

# 08-September-2026

**Added**

[Batch overlapping WhatsApp events](https://github.com/GooeyAI/gooey-server/commit/bdbbbebb)

**Fixed**

[Preserve partial reply display content](https://github.com/GooeyAI/gooey-server/commit/52d73d9a)
[Persist a superseded WhatsApp run's partial reply](https://github.com/GooeyAI/gooey-server/commit/8b9b504f)
[Coordinate WhatsApp event batching on a row lock](https://github.com/GooeyAI/gooey-server/commit/36957b2f)
[Finalize WhatsApp event batching](https://github.com/GooeyAI/gooey-server/commit/41d7ed43)
[Avoid duplicate agent knowledge controls](https://github.com/GooeyAI/gooey-server/commit/f9d2c6e2)
[Scope agent pane tab styles](https://github.com/GooeyAI/gooey-server/commit/3a93428e)
[Switch agent panes without refetching](https://github.com/GooeyAI/gooey-server/commit/a8cb0105)

# 07-September-2026

**Added**

[Stream Fireworks chat completions](https://github.com/GooeyAI/gooey-server/commit/841fd5f7)

**Fixed**

[Polish new-page suggestions](https://github.com/GooeyAI/gooey-server/commit/36868bba)

# 04-September-2026

**Added**

[Add RunTimeline component and integrate debug pane refactor](https://github.com/GooeyAI/gooey-server/commit/91e4c586)
[Open layout v2 to everyone, scoped to the recipes forked to it](https://github.com/GooeyAI/gooey-server/commit/41276e5a)
[Name a workflow's run count in About, not its owner's output](https://github.com/GooeyAI/gooey-server/commit/b28debb3)

**Fixed**

[Relativize the rail's Ask Gooey href before navigating](https://github.com/GooeyAI/gooey-server/commit/cc81ada4)
[Only leave the editor for the split when a run starts](https://github.com/GooeyAI/gooey-server/commit/7873f17f)

# 03-September-2026

**Added**

[Give the mobile sheet a menu per state](https://github.com/GooeyAI/gooey-server/commit/a962f800)

**Fixed**

[Keep the Builder panel off the tabs with no workspace](https://github.com/GooeyAI/gooey-server/commit/5f713c07)
[Put Update back in the Usage tab's bar](https://github.com/GooeyAI/gooey-server/commit/8a8a24f8)
[Keep Run and Update out of the Usage tab's bar](https://github.com/GooeyAI/gooey-server/commit/b38198cb)
[Send a v2 recipe's Examples tab to the explore gallery](https://github.com/GooeyAI/gooey-server/commit/724a32e7)
[Anonymous user runs should be saved but not started until after login](https://github.com/GooeyAI/gooey-server/commit/a0aa7a00)

# 02-September-2026

**Fixed**

[Avoid freezing admin on large JSON fields](https://github.com/GooeyAI/gooey-server/commit/7d5775e1)

# 01-September-2026

**Fixed**

[About margins](https://github.com/GooeyAI/gooey-server/commit/2fcd5a76)
