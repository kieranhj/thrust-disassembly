\ ******************************************************************************
\ ******************************************************************************
\ * App init. Relocates code and data to lower RAM. Calls game_start.
\ ******************************************************************************
\ ******************************************************************************

\ ******************************************************************************
\ * Function: main_entry
\ * Description: Program entry: inits zero page, builds tables, hooks WRCHV, sets up HW
\ ******************************************************************************

.main_entry
{
        LDX     #$FF
        TXS                                ; reset stack
        LDX     #$A7
        
    .zp_loop
        LDA     #$00
        STA     zp_base,X
        DEX
        BNE     zp_loop                    ; reset first $A7 entries of zero page to 0

        LDY     #$4F                    ; size of multiplication table array (80)
        LDX     #$00
        LDA     #$00                    ; index into multiplication table arrays
        STA     value_LO
        STA     value_HI
        
    .mult_by_8_loop                            ; create multiplication table N * 8 for 0 <= N <= $4F (79)
        LDA     value_LO
        STA     mult_by_8_LO,X    ; store low byte at $9C0
        LDA     value_HI
        STA     mult_by_8_HI,X    ; store high byte at $A10
        CLC
        LDA     value_LO
        ADC     #$08
        STA     value_LO
        LDA     value_HI
        ADC     #$00
        STA     value_HI                ; add 8 to 16-bit number stored at $70
        INX
        DEY
        BPL     mult_by_8_loop            ; loop 80 times

        LDA     WRCHV
        STA     old_wrchv
        LDA     WRCHV+1
        STA     old_wrchv+1                ; store old WRCHV directly in code at jmp_wrchv
        LDA     #LO(main_wrchv)
        STA     WRCHV
        LDA     #HI(main_wrchv)
        STA     WRCHV+1                    ; redirect WRCHV to main_wrchv
        
\\ Copy OSWORD 7 (sound) parameters to $0700 (language space)
        
        LDX     #$00
        
    .store_8_bytes_loop
        LDA     sound_data_own_gun,X        
        STA     sound_params_own_gun,X
        LDA     sound_data_explosion_1,X
        STA     sound_params_explosion_1,X
        LDA     sound_data_explosion_2,X
        STA     sound_params_explosion_2,X
        LDA     sound_data_hostile_gun,X
        STA     sound_params_hostile_gun,X
        LDA     sound_data_collect_1,X
        STA     sound_params_collect_1,X
        LDA     sound_data_collect_2,X
        STA     sound_params_collect_2,X
        LDA     sound_data_engine,X
        STA     sound_params_engine,X    
        LDA     sound_data_countdown,X
        STA     sound_params_countdown,X
        LDA     sound_data_enter_orbit,X
        STA     sound_params_enter_orbit,X
        INX
        CPX     #$08
        BNE     store_8_bytes_loop        ; loop 8 times

\\ Store angle lookup tables lower down in memory
        
        LDX     #ANGLE_MASK
        
    .store_32_bytes_loop
        LDA     lookup_angle_to_y_FRAC,X
        STA     angle_to_y_FRAC,X
        LDA     lookup_angle_to_y_INT,X
        STA     angle_to_y_INT,X
        LDA     lookup_angle_to_x_FRAC,X
        STA     angle_to_x_FRAC,X
        LDA     lookup_angle_to_x_INT,X
        STA     angle_to_x_INT,X
        DEX
        BPL     store_32_bytes_loop        ; loop 32 times

\\ Relocate game entry code to $0400
        
        LDA     #LO(game_entry_relocated)
        STA     relocate_src_ptr
        LDA     #HI(game_entry_relocated)
        STA     relocate_src_ptr+1                ; relocate_src_ptr = $3DB3
        LDA     #LO(game_entry)
        STA     relocate_dest_ptr
        LDA     #HI(game_entry)
        STA     relocate_dest_ptr+1                ; relocate_dest_ptr = $0400
        LDY     #$00
        LDX     #$03                            ; copy 3 pages
        
    .relocate_0400_loop
        LDA     (relocate_src_ptr),Y
        STA     (relocate_dest_ptr),Y
        INY
        BNE     relocate_0400_loop

        INC     relocate_src_ptr+1
        INC     relocate_dest_ptr+1
        DEX
        BNE     relocate_0400_loop            ; copy 3 pages from $3DB3 to $0400

        LDA     #$08
        LDX     #LO(envelope_1)
        LDY     #HI(envelope_1)
        JSR     OSWORD                        ; ENVELOPE at $3E62

        LDA     #$08
        LDX     #LO(envelope_2)
        LDY     #HI(envelope_2)
        JSR     OSWORD                        ; ENVELOPE at $3E70

        LDA     #$08
        LDX     #LO(envelope_3)
        LDY     #HI(envelope_3)
        JSR     OSWORD                        ; ENVELOPE at $3E7D

        LDA     #$08
        LDX     #LO(envelope_4)
        LDY     #HI(envelope_4)
        JSR     OSWORD                        ; ENVELOPE at $3E8B

        LDX     #$00
        
    .store_at_0100_loop
        LDA     high_score_table_relocated,X
        STA     high_score_table,X
        INX
        BPL     store_at_0100_loop            ; store 128 bytes at $0100

        LDX     #$7D                        ; 126 bytes
        
    .store_at_0900_loop
        LDA     in_game_messages_relocated,X
        STA     in_game_messages,X
        DEX
        BPL     store_at_0900_loop

        LDA     #$04
        STA     level_hostile_gun_probability

\\ Write MODE 7 instructions
        
        LDA     #LO(mode_7_instructions)
        STA     relocate_src_ptr
        LDA     #HI(mode_7_instructions)
        STA     relocate_src_ptr+1            ; set relocate_src_ptr to mode_7_instructions

        LDA     #$13
        JSR     OSBYTE                        ; *FX 19 - wait for vsync

        LDY     #$00
        
    .write_chars_loop
        LDA     (relocate_src_ptr),Y
        CMP     #$FF                        ; stop when hitting $FF
        BEQ     wait_for_spacebar

        JSR     jmp_wrchv                    ; write char

        INY
        BNE     write_chars_loop

        INC     relocate_src_ptr+1
        JMP     write_chars_loop            ; write chars until reach $FF

    .wait_for_spacebar
        LDA     #$0F
        LDX     #$00
        JSR     OSBYTE                        ; *FX 15,0 - flush all buffers

        JSR     OSRDCH                        ; wait for keypress

        CMP     #ASCII_space                ; 32 = space bar
        BNE     wait_for_spacebar            ; wait until spacebar is pressed

        JMP     game_entry                    ; jump to game start at $0400
}

\ ******************************************************************************
\ * Function: game_entry_relocated
\ * Description: Actually executes at $0400 after relocation
\ ******************************************************************************

.game_entry_relocated                    ; 
{
        LDA     #LO(status_bar_bytes)
        STA     relocate_src_ptr
        LDA     #HI(status_bar_bytes)
        STA     relocate_src_ptr+1
        LDA     #LO(SCREEN_BASE_ADDR)
        STA     relocate_dest_ptr    
        LDA     #HI(SCREEN_BASE_ADDR)
        STA     relocate_dest_ptr+1

\\ No longer need main_entry code so can overwrite it
\\ This is copying 2 character rows of MODE 1 (status bar at top of screen)
\\ Can't see it because we're not in right mode yet
        
        LDY     #$00
        LDX     #$05                    ; copy 5 pages (1280 bytes) from $4212 over $3C80 (main_entry)
        
    .copy_5_pages_loop
        LDA     (relocate_src_ptr),Y
        STA     (relocate_dest_ptr),Y
        INY
        BNE     copy_5_pages_loop

        INC     relocate_src_ptr+1
        INC     relocate_dest_ptr+1
        DEX
        BNE     copy_5_pages_loop

        JSR     clear_screen_and_init

        LDA     #$13
        JSR     OSBYTE                    ; *FX 19 - wait vsync

        LDA     #$90
        JSR     OSBYTE                    ; *FX $90 - *TV - obtain interlace status

        TYA
        EOR     #$01                    ; invert interlace status
        AND     #$01                    ; keep only that bit
        STA     interlace_status_bit    ; store at $04A8
        LDA     #$90
        JSR     OSBYTE                    ; *FX $90 - *TV

        LDA     #$13
        JSR     OSBYTE                    ; *FX 19 - wait for vsync

        LDX     #$0D                    ; write R13-R0 to 6845
        
    .set_crtc_reg_loop
        STX     SHEILA_6845_Register    ; store register number
        LDA     crtc_regs,X                ; load crtc registers
        STA     SHEILA_6845_Value        ; store register value
        DEX
        BPL     set_crtc_reg_loop                    ;

        LDA     #$9A
        LDX     #$D8
        LDY     #$00
        JSR     OSBYTE                    ; *FX 154,216

        LDA     #$D8
        STA     SHEILA_Video_ULA        ; set ULA to MODE 1

        LDA     IRQ1V
        STA     old_irq1v
        LDA     IRQ1V+1
        STA     old_irq1v+1                ; store IRQ1V

        SEI                                ; disable interrupts
        LDA     #LO(irq1_handler)
        STA     IRQ1V
        LDA     #HI(irq1_handler)
        STA     IRQ1V+1                    ; set IRQ1V to irq1_handler
        CLI                                ; enable interrupts

        LDA     #$18
        STA     SHEILA_System_VIA_Interrupt_Enable        ; disable CB1, CB2 interrupts
        
        LDX     #$00
        
    .set_palette_loop
        LDA     palette_table,X            ; load palette entry
        CMP     #$FF
        BEQ     done_set_palette_loop    ; finish when reaching $FF

        STA     SHEILA_PaletteReg        ; store palette register
        INX
        BNE     set_palette_loop        ; loop

    .done_set_palette_loop
        JSR     clear_screen_and_init
        JMP     game_start
}

\ ******************************************************************************
\ ******************************************************************************
\ * Data to be relocated lower down in memory after load before game start
\ ******************************************************************************
\ ******************************************************************************

.palette_table_relocated
{
        EQUB    $07,$17,$47,$57,$24,$34,$64,$74
        EQUB    $86,$96,$C6,$D6,$A5,$B5,$E5,$F5
        EQUB    $FF
}

.crtc_regs_relocated
{
        EQUB    127                     ; R0=Horizontal total-1
        EQUB    SCREEN_WIDTH_CHARS      ; R1=Horizontal displayed
        EQUB    94                      ; R2=Hsync pos
        EQUB    $28                     ; R3=Hsync width
        EQUB    38                      ; R4=Vertical total-1
        EQUB    $00                     ; R5=Vertical total adjust
        EQUB    SCREEN_HEIGHT_ROWS      ; R6=Vertical displayed
        EQUB    33                      ; R7=Vertical sync pos
        EQUB    $01                     ; R8=Interlace on
        EQUB    7                       ; R9=Scanlines per character
        EQUB    $67                     ; R10=Cursor start
        EQUB    $08                     ; R11=Cursor end
        EQUB    HI(SCREEN_BASE_ADDR/8)  ; R12=Screen start high
        EQUB    LO(SCREEN_BASE_ADDR/8)  ; R13=Screen start low
        EQUB    $FF
}

\ ******************************************************************************
\ * Sound envelopes
\ ******************************************************************************

.envelope_1
        EQUB    $01,$02,$FB,$FD,$FB,$02,$03,$32
        EQUB    $7E,$F9,$F9,$F4,$7E,$00
        
.envelope_2
        EQUB    $02,$02
        EQUB    $FF,$00,$01,$09,$09,$09,$00,$00
        EQUB    $00,$01,$01
        
.envelope_3
        EQUB    $03,$04,$00,$00,$00
        EQUB    $01,$01,$01,$7E,$FC,$FE,$FC,$7E
        EQUB    $6E
        
.envelope_4
        EQUB    $04,$01,$FF,$FF,$FF,$12,$12
        EQUB    $12,$32,$F4,$F4,$F4,$6E,$46

\ ******************************************************************************
\ * Sound parameter blocks
\ ******************************************************************************

.sound_data_own_gun
        EQUB    $12,$00,$01,$00,$50,$00,$02,$00

.sound_data_explosion_1
        EQUB    $11,$00,$02,$00,$96,$00,$64,$00

.sound_data_explosion_2
        EQUB    $10,$00,$03,$00,$07,$00,$64,$00

.sound_data_hostile_gun
        EQUB    $13,$00,$04,$00,$1E,$00,$14,$00

.sound_data_collect_1
        EQUB    $02,$00,$F1,$FF,$BE,$00,$01,$00

.sound_data_collect_2
        EQUB    $02,$00,$00,$00,$BE,$00,$02,$00

.sound_data_engine
        EQUB    $10,$00,$F6,$FF,$05,$00,$03,$00

.sound_data_countdown
        EQUB    $02,$00,$F1,$FF,$96,$00,$01,$00

.sound_data_enter_orbit
        EQUB    $12,$00,$03,$00,$B9,$00,$01,$00

\ ******************************************************************************
\ * High score table
\ ******************************************************************************

.high_score_table_relocated
{
        EQUB    $00,$00,$02                    ; three-byte BCD number
        EQUS    "   SPACELORD "
        
        EQUB    $00,$50,$01
        EQUS    "   ADMIRAL   "
        
        EQUB    $00,$00,$01
        EQUS    "   COMMODORE "
        
        EQUB    $00,$50,$00
        EQUS    "   CAPTAIN   "
        
        EQUB    $00,$20,$00
        EQUS    "   PILOT     "
        
        EQUB    $00,$15,$00
        EQUS    "   CADET     "
        
        EQUB    $00,$10,$00
        EQUS    "   NOVICE    "
        
        EQUB    $00,$05,$00
        EQUS    "   MENACE    "
}

\ ******************************************************************************
\ * Look up table - converts angle to 16-bit X & Y values in Q2.8 format
\ *
\ * Description:
\ *   These tables convert a discrete 32‑step angle into signed fixed‑point
\ *   X and Y components.  Together, INT + FRAC form a signed Q7.8 value:
\ *
\ *     value = INT + FRAC / 256
\ *
\ *   Angle index:
\ *     0  = pointing straight up
\ *     8  = pointing right
\ *     16 = pointing down
\ *     24 = pointing left
\ *     angles increase clockwise
\ *
\ *   Geometry:
\ *     X ≈  1.25 * sin(theta)
\ *     Y ≈ -2.5  * cos(theta)
\ *
\ *   The unequal amplitudes deliberately encode an ellipse rather than
\ *   a circle.  This asymmetry is relied upon elsewhere in the physics
\ *   (e.g. distance comparison and axis weighting).
\ ******************************************************************************

; ---------------------------------------------------------------------------
; Y component – fractional byte (Q7.8)
; Values are the fractional part of approximately:
;   -2.5 * cos(i * 2π / 32)
; ---------------------------------------------------------------------------

.lookup_angle_to_y_FRAC
        EQUB    $80,$8D,$B1,$EC,$3C,$9D,$0C,$84
        EQUB    $00,$7C,$F4,$63,$C4,$14,$4F,$73
        EQUB    $80,$73,$4F,$14,$C4,$63,$F4,$7C
        EQUB    $00,$84,$0C,$9D,$3C,$EC,$B1,$8D

; ---------------------------------------------------------------------------
; Y component – integer byte (Q7.8 signed)
; Combined with *_FRAC gives Y magnitude up to about ±2.5.
; ---------------------------------------------------------------------------

.lookup_angle_to_y_INT
        EQUB    $FD,$FD,$FD,$FD,$FE,$FE,$FF,$FF
        EQUB    $00,$00,$00,$01,$01,$02,$02,$02
        EQUB    $02,$02,$02,$02,$01,$01,$00,$00
        EQUB    $00,$FF,$FF,$FE,$FE,$FD,$FD,$FD

; ---------------------------------------------------------------------------
; X component – fractional byte (Q7.8)
; Values are the fractional part of approximately:
;   +1.25 * sin(i * 2π / 32)
; ---------------------------------------------------------------------------

.lookup_angle_to_x_FRAC
        EQUB    $00,$3E,$7A,$B1,$E2,$0A,$27,$39
        EQUB    $40,$39,$27,$0A,$E2,$B1,$7A,$3E
        EQUB    $00,$C2,$86,$4F,$1E,$F6,$D9,$C7
        EQUB    $C0,$C7,$D9,$F6,$1E,$4F,$86,$C2

; ---------------------------------------------------------------------------
; X component – integer byte (Q7.8 signed)
; Combined with *_FRAC gives X magnitude up to about ±1.25.
; Note X has roughly half the amplitude of Y by design.
; ---------------------------------------------------------------------------

.lookup_angle_to_x_INT
        EQUB    $00,$00,$00,$00,$00,$01,$01,$01
        EQUB    $01,$01,$01,$01,$00,$00,$00,$00
        EQUB    $00,$FF,$FF,$FF,$FF,$FE,$FE,$FE
        EQUB    $FE,$FE,$FE,$FE,$FF,$FF,$FF,$FF

\ ******************************************************************************
\ * More message strings
\ ******************************************************************************

.in_game_messages_relocated            ; if you change these you will need to update the string_ labels as these are relocated to page $0900
{
    .message_game_over
        EQUB    $50,$58,$F0
        EQUS    "Game Over"
        EQUB    $FF
        
    .message_top_8_thrusters
        EQUB    $40,$48,$FF
        EQUS    "Top Eight Thrusters"
        EQUB    $FF

    .message_congratulations
        EQUB    $60,$48,$FF
        EQUS    "Congratulations"
        EQUB    $FF

    .message_enter_name
        EQUB    $30,$63,$F0
        EQUS    "Please enter your name"
        EQUB    $FF

    .message_press_spacebar
        EQUB    $D0,$60,$F0
        EQUS    "Press SPACE BAR to start"
        EQUB    $FF

    .message_out_of_fuel
        EQUB    $C0,$53,$0F
        EQUS    "Out of fuel"
        EQUB    $FF
}

\ ******************************************************************************
\ ******************************************************************************
\ * MODE 7 instruction screen
\ * Status bar graphics displayed in first two lines of MODE 1 screen
\ ******************************************************************************
\ ******************************************************************************

INCLUDE "mode7_instructions.asm"
IF _SWRAM_BUILD
\\ Safety invariant: status_bar_bytes must land >= SCREEN_BASE_ADDR.
\\ game_entry_relocated does a forward copy (status_bar_bytes -> SCREEN_BASE_ADDR,
\\ &500 bytes). Forward copy corrupts the source iff src < dst within range; with
\\ status_bar_bytes >= SCREEN_BASE_ADDR the copy is safe (src == dst is identity;
\\ src > dst writes below the read pointer). The IF below pads to equality when
\\ there's room and otherwise lets status_bar_bytes spill above SCREEN_BASE_ADDR
\\ (also safe). It must never assemble status_bar_bytes BELOW SCREEN_BASE_ADDR.
IF P% < SCREEN_BASE_ADDR
PRINT "STATUS BAR PADDING: SKIPPING ", ~(SCREEN_BASE_ADDR - P%), " BYTES"
SKIP (SCREEN_BASE_ADDR - P%)
ELSE
PRINT "STATUS BAR PADDING: app_init.asm RAN PAST SCREEN_BASE_ADDR BY ", ~(P% - SCREEN_BASE_ADDR), " BYTES (forward-copy still safe)"
ENDIF
ENDIF
INCLUDE "status_bar_bytes.asm"

\ ******************************************************************************
\ ******************************************************************************
\ * Executable entry point
\ ******************************************************************************
\ ******************************************************************************

\ ******************************************************************************
\ * Function: RELOC_START
\ * Description: Slightly modified from original code during decryption
\ ******************************************************************************

.RELOC_START
{
        LDA     BRKV
        STA     old_brkv
        LDA     BRKV+1
        STA     old_brkv+1                ; store current BRKV
        LDA     #LO(restore_brkv)
        STA     BRKV
        LDA     #HI(restore_brkv)
        STA     BRKV+1                    ; set BRKV to point at restore_brkv
        LDA     BYTEV+1
        BPL     eor_everything            ; check OSBYTE vectored through OS otherwise bail out

        LDA     #$00
        LDX     #$FF
        LDY     #$FF
        JSR     OSBYTE                    ; *FX 0,255,255 - identify OS

        CPX     #$00
        BEQ     restore_brkv            ; check for OS 1.00 / Electron

        SEI                                ; disable interrupts
        LDA     DEFVEC+1
        STA     boot_read_ptr
        LDA     DEFVEC+2
        STA     boot_read_ptr+1            ; load default vector table
        LDY     DEFVEC                    ; presume size of vector table?
        
    .userv_loop
        LDA     (boot_read_ptr),Y
        STA     USERV,Y                    ; restore all default vectors
        DEY
        BNE     userv_loop

        CLI                                ; enable interrupts
        LDA     #$EA
        LDX     #$00
        LDY     #$00
        JSR     OSBYTE                    ; *FX &EA,0,0 - disable Tube

        LDA     #$8C
        LDX     #$0C
        LDY     #$00
        JSR     OSBYTE                    ; *FX &8C,0,0 - *TAPE 1200

        LDA     #$C8
        LDX     #$03
        LDY     #$00
        JSR     OSBYTE                    ; *FX &C8,3,0 - disable ESCAPE, memory cleared on BREAK

        LDA     #$04
        LDX     #$01
        JSR     OSBYTE                    ; *FX 4,1,0 - disable cursor editing, edit keys give ASCII codes

        LDA     #$E1
        LDX     #$00
        LDY     #$00
        JSR     OSBYTE                    ; *FX &E1,0,0 - ignore FN keys

    .restore_brkv
        LDA     old_brkv
        STA     BRKV
        LDA     old_brkv+1
        STA     BRKV+1                    ; restore old BRKV

        LDA     #LO(LOAD_ADDR)            ; is $01 in original source as relocates from $1A01
        STA     boot_read_ptr
        LDA     #HI(LOAD_ADDR)
        STA     boot_read_ptr+1           ; set boot_read_ptr to &1A01
        LDA     #LO(NATIVE_ADDR)
        STA     boot_write_ptr
        LDA     #HI(NATIVE_ADDR)
        STA     boot_write_ptr+1          ; set boot_write_ptr to &0A60
        IF _SWRAM_BUILD
        LDX     #HI(NATIVE_END+&FF)-HI(NATIVE_START)
        ELSE
        LDX     #$3D
        ENDIF

    .relocate
        LDY     #$00
        
    .relocate_loop
        LDA     (boot_read_ptr),Y
        STA     (boot_write_ptr),Y
        DEY
        BNE     relocate_loop

        INC     boot_read_ptr+1
        INC     boot_write_ptr+1
        DEX
        BNE     relocate                ; relocate &3D pages (~16k) from &1A01 to &0A60

        IF _SWRAM_BUILD
        JMP     copy_up_swram
        ELSE
        JMP     main_entry                ; jump to entry
        ENDIF
}

\ ******************************************************************************
\ * Function: eor_everything
\ * Description: Decrypts/decodes game code by EORing memory pages with a key
\ ******************************************************************************

.eor_everything
{
        LDA     #$01
        STA     boot_read_ptr
        LDA     #$1A
        STA     boot_read_ptr+1
        LDX     #$3D
        
    .eor_loop
        LDA     (boot_read_ptr),Y
        EOR     (boot_read_ptr+1),Y
        STA     (boot_read_ptr),Y
        DEY
        BNE     eor_loop

        INC     boot_read_ptr+1
        DEX
        BNE     eor_loop

        RTS
}
