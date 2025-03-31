/*
 * bai5.2 giao tiep LCD 4bit.c
 *
 * Created: 3/31/2025 10:15:38 AM
 * Author : Lap4all
 */ 

#define F_CPU 16000000ul
#include <avr/io.h>
#include <string.h>
#include "util/delay.h"

#define LCD_dir  DDRC
#define LCD_port PORTC

#define RS 0
#define EN 1

void LCD_init(void);
void LCD_command(unsigned char);
void LCD_char(unsigned char);
void LCD_string(char*);
void LCD_string_xy(char , char , char*);

int main(void)
{
    LCD_init();
    LCD_string("hhhhh");
	
	LCD_string_xy(2,5,"bye");
    
    while (1) 
    {
    }
}

void LCD_init(void)
{
    LCD_dir = 0xFF; // ??t PortC là output
    _delay_ms(40); // ??i 40ms ?? LCD kh?i t?o
    
    LCD_command(0x28); // Ch? ?? 4-bit, 2 dòng
    LCD_command(0x02); // ??a con tr? v? ??u
    LCD_command(0x0C); // B?t hi?n th?, t?t con tr? nh?p nháy
    LCD_command(0x01); // Xóa màn hình
    _delay_ms(2); // ??i 2ms sau l?nh xóa
}

void LCD_command(unsigned char cmnd)
{
    LCD_port = (LCD_port & 0x0F) | (cmnd & 0xF0); // G?i 4 bit cao
    LCD_port &= ~(1 << RS); // RS = 0, ghi l?nh
    LCD_port |= (1 << EN);  // EN = 1, kích ho?t
    _delay_ms(1);
    LCD_port &= ~(1 << EN); // EN = 0
    _delay_ms(3);
    
    LCD_port = (LCD_port & 0x0F) | ((cmnd << 4) & 0xF0); // G?i 4 bit th?p
    LCD_port |= (1 << EN);  // EN = 1, kích ho?t
    _delay_ms(1);
    LCD_port &= ~(1 << EN); // EN = 0
    _delay_ms(3);
}

void LCD_char(unsigned char data)
{
    LCD_port = (LCD_port & 0x0F) | (data & 0xF0);
    LCD_port |= (1 << RS);  // RS = 1, ghi d? li?u
    LCD_port |= (1 << EN);
    _delay_ms(1);
    LCD_port &= ~(1 << EN);
    _delay_ms(3);
    
    LCD_port = (LCD_port & 0x0F) | (data << 4);
    LCD_port |= (1 << EN);
    _delay_ms(1);
    LCD_port &= ~(1 << EN);
    _delay_ms(2);
}

void LCD_string(char *str)
{
    int len = strlen(str);
    for(int i = 0; i < len; i++)
    {
        LCD_char(str[i]);
    }
}

void LCD_string_xy(char row , char pos, char*str)
{
	if (row == 1 && pos < 16)
	LCD_command((pos & 0x0F) | 0x80);
	else if (row == 2 && pos < 16)
	LCD_command((pos & 0x0F) | 0xC0);
	LCD_string(str);
}