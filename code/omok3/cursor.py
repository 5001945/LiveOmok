import pygame

cursor_zero_strings = (               #sized 40x40
  "XX                      ",
  "XXX                     ",
  "XXXX                    ",
  "XX.XX                   ",
  "XX..XX                  ",
  "XX...XX                 ",
  "XX....XX                ",
  "XX.....XX               ",
  "XX......XX              ",
  "XX.......XX             ",
  "XX........XX            ",
  "XX........XXX           ",
  "XX......XXXXX           ",
  "XX.XXX..XX              ",
  "XXXX XX..XX             ",
  "XX   XX..XX             ",
  "     XX..XX             ",
  "      XX..XX            ",
  "      XX..XX            ",
  "       XXXX             ",
  "       XX               ",
  "                        ",
  "                        ",
  "                        ")
cursor_zero_surface = pygame.Surface((40, 40), flags=pygame.SRCALPHA)
cursor_zero_surface.fill((0, 0, 0, 0))
cursor_zero_image = pygame.image.load("cursor_0_binary.png").convert_alpha()
cursor_zero_surface.blit(cursor_zero_image, (0, 0))
# cursor_one: pygame.Cursor = pygame.cursors.Cursor(
#     (24, 24),
#     (0, 0),
#     *pygame.cursors.compile(cursor_one_strings)
# )
cursor_zero = pygame.Cursor((20, 20), cursor_zero_surface)
